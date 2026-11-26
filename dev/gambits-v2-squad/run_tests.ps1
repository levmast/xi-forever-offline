# GambitsV2: every automated check for the addon and its server side, in one run. Reads only; temporary files go to -Work.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File dev\gambits-v2-squad\run_tests.ps1 -Server <server repo checkout>
#
# -Server   a checkout of the server repo with the GambitsV2 changes (modules/custom/lua, scripts/, sql/ are read)
# -BaseRef  the server revision WITHOUT the GambitsV2 hooks, for the "built-in behaviour unchanged" comparison
#           (default origin/dev; its modules/custom/lua/squad.lua is read with git show)
# -RuleSetData  optional: a COPY of a squad_rulesets_data.lua to load (never a live server's file)
# Tools are found on PATH unless given: luajit, lua (5.4), luac (5.4), python (3.8+), git.
# Lua 5.4: the server's !squad command wrapper uses the LuaJIT/5.1 global unpack (the server runs LuaJIT), so the 5.4
# runs get  -e "unpack = unpack or table.unpack"  on the command line. No test or server file is changed for it.
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [string]$BaseRef = 'origin/dev',
    [string]$Kit = '',
    [string]$Work = (Join-Path ([IO.Path]::GetTempPath()) ('gambitsv2-tests-' + (Get-Random))),
    [string]$RuleSetData = '',
    [string]$LuaJitExe = 'luajit', [string]$LuaExe = 'lua', [string]$LuacExe = 'luac', [string]$PythonExe = 'python', [string]$GitExe = 'git'
)
$ErrorActionPreference = 'Stop'
if (-not $Kit) { $Kit = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }   # (Windows PowerShell 5.1: $PSScriptRoot is empty in param defaults)
$lua = Join-Path $Server 'modules\custom\lua'
$gl  = Join-Path $Server 'scripts\globals\gambits.lua'
$ja  = Join-Path $Server 'scripts\enum\job_ability.lua'
$add = Join-Path $Kit 'addons-src\Gambits'
$t   = $PSScriptRoot
New-Item -ItemType Directory -Force $Work | Out-Null
$orig = Join-Path $Work 'squad_base.lua'
$tmp = [IO.Path]::GetTempFileName()
cmd /c "`"$((Get-Command $GitExe).Source)`" -C `"$Server`" show ${BaseRef}:modules/custom/lua/squad.lua > `"$tmp`""
if ($LASTEXITCODE -ne 0) { throw "git show ${BaseRef}:modules/custom/lua/squad.lua failed" }
Move-Item $tmp $orig -Force
$data = @()
if ($RuleSetData) { $copy = Join-Path $Work 'squad_rulesets_data.copy.lua'; Copy-Item -LiteralPath $RuleSetData -Destination $copy; $data = @($copy) }
$fail = 0
function Write-Result($name, $code) { if ($code -ne 0) { $script:fail++ }; '{0,-60} {1}' -f $name, $(if ($code -eq 0) { 'OK' } else { "FAIL ($code)" }) }

'== syntax (luac -p, luajit -bl)'
$files = @('squad.lua', 'gambits_squad.lua', 'squad_rulesets.lua', 'squad_rulesets_store.lua', 'squad_ability_rules.lua', 'squad_ja_jobs_data.lua', 'squad_spell_jobs_data.lua', 'squad_jobs.lua') | ForEach-Object { Join-Path $lua $_ }
$files += Get-ChildItem $add -Filter *.lua | ForEach-Object FullName
foreach ($f in $files) {
    & $LuacExe -p $f; $a = $LASTEXITCODE
    & $LuaJitExe -bl $f > $null; $b = $LASTEXITCODE
    Write-Result ('syntax ' + (Split-Path $f -Leaf)) ([int]($a -ne 0 -or $b -ne 0))
}

'== generated data is up to date with the server sources (--check)'
& $PythonExe -I (Join-Path $t 'make_squad_ja_jobs.py') --check (Join-Path $Server 'sql\abilities.sql') (Join-Path $lua 'squad_ja_jobs_data.lua'); Write-Result 'squad_ja_jobs_data.lua' $LASTEXITCODE
& $PythonExe -I (Join-Path $t 'make_squad_spell_jobs.py') --check (Join-Path $Server 'sql\spell_list.sql') (Join-Path $Server 'scripts\enum\magic.lua') (Join-Path $Server 'sql\item_basic.sql') (Join-Path $lua 'squad_spell_jobs_data.lua'); Write-Result 'squad_spell_jobs_data.lua' $LASTEXITCODE
& $PythonExe -I (Join-Path $t 'make_squad_spell_jobs.py') --check-trusts (Join-Path $Server 'sql\spell_list.sql') (Join-Path $Server 'scripts\enum\magic.lua') (Join-Path $add 'trust_spells.lua'); Write-Result 'addon trust_spells.lua' $LASTEXITCODE
& $PythonExe -I (Join-Path $t 'make_gambits_addon_data.py') --check $Server (Join-Path $add 'gambits_data.lua'); Write-Result 'addon gambits_data.lua' $LASTEXITCODE

Push-Location $t
try {
    foreach ($run in @(@{ name = 'LuaJIT'; exe = $LuaJitExe; pre = @() }, @{ name = 'Lua 5.4'; exe = $LuaExe; pre = @('-e', 'unpack = unpack or table.unpack') })) {
        "== suites, $($run.name)"
        $pre = $run.pre
        $suites = @(
            @{ n = 'addon end to end (test_gambitsv2_addon.lua)';        a = @('test_gambitsv2_addon.lua', $lua, $gl, $ja, $add, $Work) },
            @{ n = 'server !gsq (test_gambits_squad.lua)';               a = @('test_gambits_squad.lua', $lua, $gl, $ja, $add, $Work) },
            @{ n = 'Rule Sets and U13 (test_squad_rulesets.lua)';        a = @('test_squad_rulesets.lua', (Join-Path $lua 'squad.lua'), (Join-Path $lua 'squad_starter_gear.lua'), $gl, (Join-Path $lua 'squad_rulesets.lua'), $orig, $ja) },
            @{ n = 'squad.lua integration (test_squad_upstream_integration.lua)'; a = @('test_squad_upstream_integration.lua', $lua, $gl, $ja, $orig, $Work) + $data },
            @{ n = 'WAR/PLD/RDM/WS batch (test_gambits_ws_batch.lua)';  a = @('test_gambits_ws_batch.lua', $lua, $gl, $ja, $add, $Work, $Server) },
            @{ n = 'job expansion (test_gambits_jobexp.lua)';           a = @('test_gambits_jobexp.lua', $lua, $gl, $ja, $add, $Work, $Server) },
            @{ n = 'UI/UX 0.3.1 (test_gambits_uiux.lua)';               a = @('test_gambits_uiux.lua', $lua, $gl, $ja, $add, $Work, $Server) },
            @{ n = 'song tiers + import/export 0.3.3 (test_gambits_bard_io.lua)'; a = @('test_gambits_bard_io.lua', $lua, $gl, $ja, $add, $Work, $Server) },
            @{ n = 'picker list cache (test_gambits_view_cache.lua)';   a = @('test_gambits_view_cache.lua', $lua, $gl, $ja, $add, $Work, $Server) },
    @{ n = 'Save / Apply, live state, caches 0.3.4 (test_gambits_save_apply.lua)'; a = @('test_gambits_save_apply.lua', $lua, $gl, $ja, $add, $Work) },
    @{ n = 'settings follow the character, theme default 0.3.4 (test_gambits_settings_theme.lua)'; a = @('test_gambits_settings_theme.lua', $add) },
    @{ n = 'enemy family and counts, v11 (test_gambits_feedback.lua)'; a = @('test_gambits_feedback.lua', $lua, $gl, $ja, $add, $Work, $Server) },
    @{ n = 'F12 WS gear set + F13 Summoner (test_gambits_smn_wsset.lua)'; a = @('test_gambits_smn_wsset.lua', $lua, $gl, $ja, $add, $Work, $Server) }
        )
        foreach ($s in $suites) {
            $out = & $run.exe @pre @($s.a) 2>&1 | ForEach-Object { "$_" }
            $code = $LASTEXITCODE
            $out | Where-Object { $_ -match '^FAIL|^passed|sweep:' } | ForEach-Object { '    ' + $_ }
            if ($code -ne 0) { $out | Select-Object -Last 6 | ForEach-Object { '    ' + $_ } }
            Write-Result ('  ' + $s.n) $code
        }
    }
} finally { Pop-Location }
''
if ($fail -eq 0) { 'ALL OK' } else { "$fail FAILED" }
exit $fail

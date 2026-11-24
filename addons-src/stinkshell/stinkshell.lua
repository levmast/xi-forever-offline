--[[
stinkshell 1.1  (XI: Forever Offline, 2026-11-23)
An online chat room for players of every world, in a window that looks like 1999. Your screen name is your character's
name (the first player to use a name keeps it; anyone else gets Name2). Off by default; it needs the internet and the
launcher running, which carries the lines to chat.xiforever.com and back (launcher_stinkshell.py).

  /stink              open or close the chat room window
  /sl <text>          say something in the room without opening the window
  /stink who          who is in the room (the same as typing /who in the window)
Moderators type their commands in the window: /mute Name [minutes], /unmute, /kick, /ban, /unban; /login CODE once.

It talks to the launcher through three files in config/addons/stinkshell: out.txt (what you say), in.txt (what the room
says) and people.txt (who is here). Nothing from the room is ever run as a command.
]]

addon.name    = 'stinkshell';
addon.author  = 'XI: Forever Offline';
addon.version = '1.1';
addon.desc    = 'Online chat room for every XI: Forever Offline player, 1999 style. Needs the internet.';
addon.link    = 'https://xiforever.com';

require('common');

local imgui;
do
    local ok, mod = pcall(require, 'imgui');
    if ok then imgui = mod; end
end

local MAX_LINES = 300;
local S = {
    open = { true },
    input = { '' },
    lines = {},             -- { kind, screen, text }
    people = {},
    me = nil,               -- my screen name (from people.txt)
    name = nil,             -- my character's name
    offset = 0,             -- how far into in.txt we have read
    lastRead = -1000,
    unread = 0,
    scroll = false,
    sentHello = nil,
    waiting = false,        -- the launcher has not answered yet
    startedAt = os.clock(),
};

local function now() return os.clock(); end

local function dir()
    local ok, base = pcall(function() return AshitaCore:GetInstallPath(); end);
    if not ok or type(base) ~= 'string' then return nil; end
    return base .. 'config/addons/stinkshell/';
end

local function myName()
    local ok, name = pcall(function() return AshitaCore:GetMemoryManager():GetParty():GetMemberName(0); end);
    if ok and type(name) == 'string' and name:match('^%a+$') then return name; end
    return nil;
end

-- Plain printable text only, and no '|' (the field separator)
local function clean(text, limit)
    text = tostring(text or ''):gsub('[%z\1-\31\127-\255|]', ''):gsub('%s+', ' ');
    text = text:match('^%s*(.-)%s*$') or '';
    return text:sub(1, limit or 200);
end

local function addLine(kind, screen, text)
    table.insert(S.lines, { kind = kind, screen = screen, text = text });
    while #S.lines > MAX_LINES do table.remove(S.lines, 1); end
    S.scroll = true;
    if kind == 'say' and not S.open[1] then S.unread = S.unread + 1; end
end

local function write(kind, text)
    local d = dir();
    local name = S.name or myName();
    if not (d and name) then return false; end
    if ashita and ashita.fs and ashita.fs.create_directory then pcall(ashita.fs.create_directory, d); end
    local f = io.open(d .. 'out.txt', 'a');
    if not f then return false; end
    f:write(kind .. '|' .. name .. '|' .. clean(text) .. '\n');
    f:close();
    return true;
end

local function say(text)
    text = clean(text);
    if text == '' then return; end
    if not write('say', text) then
        addLine('system', '', 'Stinkshell: log in to a character first.');
    end
end

-- ---------------------------------------------------------------- reading what the launcher wrote
local function readIn()
    local d = dir();
    if not d then return; end
    local f = io.open(d .. 'in.txt', 'r');
    if f then
        local size = f:seek('end') or 0;
        if size < S.offset then S.offset = 0; end          -- the launcher started over
        if size > S.offset then
            f:seek('set', S.offset);
            local chunk = f:read('*a') or '';
            local last = chunk:match('.*()\n');              -- only whole lines; the rest is read next time
            if last then
                S.offset = S.offset + last;
                for line in chunk:sub(1, last):gmatch('[^\n]+') do
                    local _, kind, screen, text = line:match('^(%d*)|([^|]*)|([^|]*)|([^|]*)');
                    if kind then addLine(kind, screen, text); S.waiting = false; end
                end
            end
        end
        f:close();
    end
    local p = io.open(d .. 'people.txt', 'r');
    if p then
        local people = {};
        for line in p:lines() do
            local me = line:match('^#me|(.*)$');
            if me then S.me = me ~= '' and me or S.me;
            elseif line ~= '' then table.insert(people, line); end
        end
        p:close();
        S.people = people;
        S.waiting = false;
    end
end

-- ---------------------------------------------------------------- the 1999 look
local GREY     = { 0.753, 0.753, 0.753, 1 };   -- #C0C0C0, the colour of every window in 1999
local DARK     = { 0.502, 0.502, 0.502, 1 };
local WHITE    = { 1, 1, 1, 1 };
local BLACK    = { 0, 0, 0, 1 };
local NAVY     = { 0, 0, 0.502, 1 };           -- the active title bar
local NAVY_OFF = { 0.502, 0.502, 0.502, 1 };
local BLUE     = { 0, 0, 0.85, 1 };            -- other people's screen names
local RED      = { 0.8, 0, 0, 1 };             -- yours
local SYSTEM   = { 0.35, 0.35, 0.35, 1 };

local function pushColors(list)
    if not (imgui and imgui.PushStyleColor) then return 0; end
    local pushed = 0;
    for _, item in ipairs(list) do
        local id = rawget(_G, item[1]);
        if id ~= nil and pcall(imgui.PushStyleColor, id, item[2]) then pushed = pushed + 1; end
    end
    return pushed;
end

local function pushVars(list)
    if not (imgui and imgui.PushStyleVar) then return 0; end
    local pushed = 0;
    for _, item in ipairs(list) do
        local id = rawget(_G, item[1]);
        if id ~= nil and pcall(imgui.PushStyleVar, id, item[2]) then pushed = pushed + 1; end
    end
    return pushed;
end

local function colored(rgba, text, wrap)
    local n = pushColors({ { 'ImGuiCol_Text', rgba } });
    if wrap and imgui.TextWrapped then imgui.TextWrapped(text) else imgui.Text(text) end
    if n > 0 then imgui.PopStyleColor(n); end
end

local function sameLine(spacing)
    if imgui.SameLine then imgui.SameLine(0, spacing or 0); end
end

local function chatPane(width, height)
    -- (2026-11-23, Hexblood, Rysan, Frost) Ashita's imgui takes child flags here, not true/false: 'no matching function call'
    imgui.BeginChild('stinkshell_chat', { width, height }, rawget(_G, 'ImGuiChildFlags_Borders') or 1);
    for _, line in ipairs(S.lines) do
        if line.kind == 'say' then
            local mine = S.me ~= nil and line.screen == S.me;
            colored(mine and RED or BLUE, line.screen .. ':');
            sameLine(6);
            colored(BLACK, line.text, true);
        elseif line.kind == 'enter' or line.kind == 'leave' then
            colored(SYSTEM, '*** ' .. line.text, true);
        else
            colored(NAVY, line.text, true);
        end
    end
    if S.scroll and imgui.SetScrollHereY then
        imgui.SetScrollHereY(1.0);
        S.scroll = false;
    end
    imgui.EndChild();
end

local function peoplePane(width, height)
    imgui.BeginChild('stinkshell_people', { width, height }, rawget(_G, 'ImGuiChildFlags_Borders') or 1);
    colored(BLACK, 'People Here: ' .. #S.people);
    if imgui.Separator then imgui.Separator(); end
    for _, p in ipairs(S.people) do
        colored(p == S.me and RED or BLACK, p);
    end
    imgui.EndChild();
end

local function render()
    if not (imgui and imgui.Begin) or not S.open[1] then return; end
    if imgui.SetNextWindowSize then
        imgui.SetNextWindowSize({ 560, 380 }, rawget(_G, 'ImGuiCond_FirstUseEver') or 4);
    end
    local colors = pushColors({
        { 'ImGuiCol_WindowBg', GREY }, { 'ImGuiCol_ChildBg', WHITE }, { 'ImGuiCol_Border', DARK },
        { 'ImGuiCol_TitleBg', NAVY_OFF }, { 'ImGuiCol_TitleBgActive', NAVY }, { 'ImGuiCol_TitleBgCollapsed', NAVY_OFF },
        { 'ImGuiCol_Text', BLACK }, { 'ImGuiCol_FrameBg', WHITE }, { 'ImGuiCol_FrameBgHovered', WHITE },
        { 'ImGuiCol_FrameBgActive', WHITE }, { 'ImGuiCol_Button', GREY }, { 'ImGuiCol_ButtonHovered', { 0.85, 0.85, 0.85, 1 } },
        { 'ImGuiCol_ButtonActive', DARK }, { 'ImGuiCol_ScrollbarBg', { 0.87, 0.87, 0.87, 1 } },
        { 'ImGuiCol_ScrollbarGrab', GREY }, { 'ImGuiCol_ScrollbarGrabHovered', GREY }, { 'ImGuiCol_ScrollbarGrabActive', DARK },
        { 'ImGuiCol_Separator', DARK }, { 'ImGuiCol_ResizeGrip', GREY }, { 'ImGuiCol_TextSelectedBg', NAVY },
    });
    local vars = pushVars({
        { 'ImGuiStyleVar_WindowRounding', 0 }, { 'ImGuiStyleVar_ChildRounding', 0 }, { 'ImGuiStyleVar_FrameRounding', 0 },
        { 'ImGuiStyleVar_ScrollbarRounding', 0 }, { 'ImGuiStyleVar_WindowBorderSize', 2 }, { 'ImGuiStyleVar_FrameBorderSize', 1 },
        { 'ImGuiStyleVar_ChildBorderSize', 1 },
    });
    local title = 'Stinkshell - Forever Chat Room' .. (S.me and ('  [' .. S.me .. ']') or '') .. '###stinkshell';
    if imgui.Begin(title, S.open) then
        colored(BLACK, 'Welcome to Stinkshell!  Room: Forever');
        if S.waiting and now() - S.startedAt > 8 then
            sameLine(12);
            colored(RED, '(waiting for the launcher: is it open, and is Stinkshell on?)');
        end
        local w, h = 540, 340;
        if imgui.GetContentRegionAvail then
            local ok, a, b = pcall(imgui.GetContentRegionAvail);
            if ok then
                if type(a) == 'table' then w, h = a[1] or a.x or w, a[2] or a.y or h; else w, h = a or w, b or h; end
            end
        end
        local side = 130;
        chatPane(math.max(150, w - side - 8), math.max(80, h - 34));
        sameLine(8);
        peoplePane(side, math.max(80, h - 34));
        if imgui.PushItemWidth then imgui.PushItemWidth(math.max(100, w - 70)); end
        local enter = rawget(_G, 'ImGuiInputTextFlags_EnterReturnsTrue') or 32;
        local pressed = imgui.InputText('##stinkshell_say', S.input, 200, enter);
        if imgui.PopItemWidth then imgui.PopItemWidth(); end
        sameLine(6);
        if imgui.Button('Send', { 60, 0 }) then pressed = true; end
        if pressed then
            say(S.input[1]);
            S.input[1] = '';
            if imgui.SetKeyboardFocusHere then imgui.SetKeyboardFocusHere(-1); end
        end
    end
    imgui.End();
    if vars > 0 then imgui.PopStyleVar(vars); end
    if colors > 0 then imgui.PopStyleColor(colors); end
end

-- ---------------------------------------------------------------- events
local function tell(text)
    print('\31\200[\31\05Stinkshell\31\200]\30\01 ' .. text);
end

ashita.events.register('load', 'stinkshell_load', function ()
    S.waiting = true;
end);

ashita.events.register('d3d_present', 'stinkshell_present', function ()
    local t = now();
    if t - S.lastRead >= 0.5 then
        S.lastRead = t;
        local name = myName();
        if name and name ~= S.sentHello then
            S.name = name;
            if write('hello', '') then S.sentHello = name; end
        end
        pcall(readIn);
    end
    render();
end);

ashita.events.register('command', 'stinkshell_command', function (e)
    local args = e.command:args();
    if #args == 0 then return; end
    local cmd = args[1]:lower();
    if cmd == '/sl' then
        e.blocked = true;
        local text = e.command:match('^%S+%s+(.+)$');
        if text then say(text); else S.open[1] = true; end
    elseif cmd == '/stink' or cmd == '/stinkshell' then
        e.blocked = true;
        local sub = (args[2] or ''):lower();
        if sub == 'who' then
            say('/who');
            S.open[1] = true;
        else
            S.open[1] = not S.open[1];
            if S.open[1] then
                if S.unread > 0 then tell(S.unread .. ' new line(s) while the window was closed.'); end
                S.unread = 0;
            end
        end
    end
end);

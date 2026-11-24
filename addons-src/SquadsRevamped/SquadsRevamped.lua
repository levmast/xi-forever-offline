--[[
SquadsRevamped (shell). Draws nothing, registers no command, prints nothing.
It only keeps the saved Revamped switch readable (rv_switch.lua) so the Revamped Squads package has a place to plug in.
When the full Squads Revamped package is installed over this folder, its files replace this one (same names, same layout).
The switch file is shared with the launcher: <Ashita>\config\addons\revamped\choice.txt
]]

addon.name = 'SquadsRevamped'
addon.author = 'XI: Forever Offline'
addon.version = '0.0.1-shell'
addon.desc = 'Squads Revamped shell: nothing to see until the Revamped package is installed.'
addon.link = ''

require('common')

local imgui = require('imgui')
local ok, RV = pcall(require, 'rv_switch')

ashita.events.register('d3d_present', 'sr_shell_present', function()
    if ok then pcall(RV.tick, imgui) end
end)

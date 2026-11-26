-- Checks the server menu's profile sheet icon path without a game.
-- ffi, d3d8 and the game resources are small fakes.
--   python runlua.py test_servermenu_icons.lua ../addons-src/servermenu/servermenu.lua
local PATH = arg[1] or '../../addons-src/servermenu/servermenu.lua'
local passed, failed = 0, 0
local function check(c, l) if c then passed = passed + 1 else failed = failed + 1 io.write('FAIL: ', l, '\n') end end

local TICK = 1000000
local handlers, texts, images, sent, clicks, buttons = {}, {}, {}, {}, {}, {}
local iconCreations = 0
local drawList = {}
function drawList:AddRectFilled() end
function drawList:AddText() end

-- ---- the two pieces of the game the icon loader talks to ----
local fakeFfi = {
    new = function () return setmetatable({ [0] = 1 }, { __index = function () return 1 end }) end,
    cast = function () return 4242 end,
    C = {
        D3DXCreateTextureFromFileInMemoryEx = function () iconCreations = iconCreations + 1; return 0 end,
        D3DFMT_A8R8G8B8 = 0, D3DPOOL_MANAGED = 0, D3DX_DEFAULT = 0,
    },
}
package.loaded['ffi'] = fakeFfi
package.loaded['d3d8'] = {
    get_device = function () return 1 end,
    gc_safe_release = function () return 1 end,
}

local imgui = setmetatable({}, { __index = function () return function () end end })
function imgui.Begin() return true end
function imgui.End() end
function imgui.Text(s) texts[#texts + 1] = tostring(s) end
function imgui.TextWrapped(s) texts[#texts + 1] = tostring(s) end
function imgui.TextColored(_, s) texts[#texts + 1] = tostring(s) end
function imgui.Image(ptr, size) images[#images + 1] = { ptr = ptr, size = size and size[1] } end
function imgui.Button(label)
    buttons[#buttons + 1] = label
    if clicks[label] then clicks[label] = nil; return true end
    return false
end
function imgui.GetCursorScreenPos() return { 10, 20 } end
function imgui.SetCursorScreenPos() end
function imgui.GetContentRegionAvail() return { 456, 300 } end
function imgui.GetWindowDrawList() return drawList end
function imgui.CalcTextSize(s) return { #tostring(s) * 6, 13 } end
function imgui.ColorConvertFloat4ToU32() return 0xFFFFFFFF end
function imgui.SameLine() end
function imgui.Dummy() end
function imgui.BeginGroup() end
function imgui.EndGroup() end
function imgui.Separator() end
function imgui.SetNextWindowSize() end
function imgui.SetNextWindowSizeConstraints() end
function imgui.SetNextWindowPos() end
function imgui.SetNextWindowFocus() end
function imgui.PushStyleColor() end
function imgui.PopStyleColor() end
function imgui.PushStyleVar() end
function imgui.PopStyleVar() end
function imgui.NewLine() end
function imgui.GetMainViewport() return { GetCenter = function () return { x = 400, y = 300 } end } end

for name, value in pairs({
    ImGuiCol_Text = 0, ImGuiCol_WindowBg = 2, ImGuiCol_Border = 3, ImGuiCol_Separator = 4,
    ImGuiCol_TitleBg = 5, ImGuiCol_TitleBgActive = 6, ImGuiCol_Button = 21,
    ImGuiCol_ButtonHovered = 22, ImGuiCol_ButtonActive = 23, ImGuiCol_PlotHistogram = 40,
    ImGuiStyleVar_WindowRounding = 30, ImGuiStyleVar_ChildRounding = 31, ImGuiStyleVar_FrameRounding = 32,
    ImGuiStyleVar_WindowPadding = 33, ImGuiStyleVar_ItemSpacing = 34, ImGuiStyleVar_FramePadding = 35,
    ImGuiCond_FirstUseEver = 4, ImGuiWindowFlags_NoCollapse = 1, ImGuiWindowFlags_AlwaysAutoResize = 2,
}) do rawset(_G, name, value) end

addon = {}
ashita = {
    events = { register = function (name, id, fn) handlers[name] = fn end },
    time = { get_tick64 = function () return TICK end },
    fs = { create_directory = function () end },
}
AshitaCore = {
    GetChatManager = function () return {
        IsInputOpen = function () return false end,
        QueueCommand = function (_, kind, command) sent[#sent + 1] = command end,
    } end,
    GetInstallPath = function () return os.tmpname() .. '/' end,
    GetDirect3DDevice = function () return 1 end,
    GetResourceManager = function () return {
        GetItemById = function (_, id)
            if id == 1234 then return { Bitmap = 1, ImageSize = 1 } end
            return nil
        end,
    } end,
}

package.preload['common'] = function () return true end
package.preload['imgui'] = function () return imgui end
print = function () end

assert(loadfile(PATH))()
handlers.load()
-- (servermenu 1.27) what a mate wears is on the profile's Gear view (/sq gear); a worn piece is a button "Slot:  Name"
handlers.command({ command = { args = function () return { '/sq', 'gear', '1' } end } })

local function feed(line)
    handlers.text_in({ message = 'squadsheet:' .. line })
end

TICK = TICK + 100
-- (1.27) the squad list is not fed here, so the menu cannot tell from the name whose sheet this is: the answer says
-- its slot, as the milestone's server does (an answer without it is held back until the squad list names the slot;
-- that case is in dev/squad-tests/test_squad_menu_ui.lua, section 9). An older menu skips the line.
feed('slot|1')
feed('hdr|Kasumi|WAR|22|MNK|11|tank|balanced|Mithra|15')
feed('eq|0|Main|onion_dagger|1234')
feed('eq|1|Sub|Empty|0')
feed('end')
handlers.d3d_present()

check(#images == 1, 'the item with a real id gets one icon: ' .. tostring(#images))
check(images[1] and images[1].ptr == 4242, 'the texture pointer is handed to ImGui')
check(images[1] and images[1].size == 26, 'the icon is drawn at 26x26')
check(iconCreations == 1, 'the item bitmap is loaded once: ' .. tostring(iconCreations))
local joined = table.concat(texts, '\n') .. '\n' .. table.concat(buttons, '\n')
check(joined:find('Onion Dagger', 1, true) ~= nil, 'the underscored item name is shown as readable words')
check(joined:find('onion_dagger', 1, true) == nil, 'the underscore form is not shown')
check(joined:find('Onion Dagger|1234', 1, true) == nil, 'the raw id is not shown next to the name')

-- The header switches are buttons, and clicking one sends the squad command.
clicks['melee##sheetsw1melee'] = true
handlers.d3d_present()
TICK = TICK + 700
handlers.d3d_present()
TICK = TICK + 700
handlers.d3d_present()
check(table.concat(sent, '\n'):find('!squad sw 1 melee off', 1, true) ~= nil, 'clicking melee sends the toggle command; sent: ' .. table.concat(sent, '; '))

images = {}
TICK = TICK + 6000
handlers.d3d_present()
check(iconCreations == 1, 'a sheet refresh reuses the cached texture: ' .. tostring(iconCreations))
check(#images >= 1, 'and the icon is still drawn after the refresh')

io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)

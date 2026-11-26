--[[
xifo_ui - the small shared look of the XI: Forever Offline windows (Squads menu, Profile, Spells, Gambits).

One file, kept as IDENTICAL copies in addons-src/servermenu/ and addons-src/Gambits/ (dev/squad-tests/test_xifo_ui.lua
fails when they differ). Each add-on loads its own copy, so each still loads alone. Nothing here talks to the server or
reads the game: it is palettes, a few ImGui helpers that cannot leave ImGui's stacks unbalanced, and the small file that
carries a character's chosen theme from one add-on to the other.

Palettes: the colours of FFXIPort 1.2.0 (ffxiport/ui/theme.lua, Copyright (C) 2026 wildthing, GPL-3.0-only), value for
value as the Gambits editor has had them. Crimson is the default for a NEW installation; nothing here ever changes a
saved choice. The keys on / onHi / warn / busy are additions (derived from the same palette's own values; in the Squad
theme they are the Squads menu's own colours), no older key was changed.
]]

local U = { VERSION = 1 }

local function rgba(r, g, b, a)
    return { r, g, b, a or 1.0 }
end

local function times(c, f)
    return { math.min(c[1] * f, 1.0), math.min(c[2] * f, 1.0), math.min(c[3] * f, 1.0), c[4] }
end
U.rgba, U.times = rgba, times

-- ---------------------------------------------------------------- palettes
U.THEMES = {
    classic = {
        window = rgba(0.105, 0.095, 0.082), panel = rgba(0.105, 0.095, 0.082), header = rgba(0.23, 0.18, 0.10),
        button = rgba(0.24, 0.19, 0.10), border = times(rgba(0.23, 0.18, 0.10), 1.25), text = rgba(0.91, 0.89, 0.80),
        gold = rgba(0.82, 0.63, 0.22), tabSel = rgba(0.53, 0.42, 0.09), rowSel = rgba(0.53, 0.42, 0.09),
        muted = rgba(0.47, 0.44, 0.36), secondary = rgba(0.64, 0.60, 0.50), goGold = rgba(0.82, 0.62, 0.10),
        goText = rgba(0.10, 0.08, 0.05), ok = rgba(0.55, 0.80, 0.45), bad = rgba(0.90, 0.35, 0.30), dot = rgba(0.86, 0.67, 0.22),
    },
    squad = {
        window = rgba(0.067, 0.075, 0.106), panel = rgba(0.110, 0.118, 0.161), header = rgba(0.150, 0.165, 0.220),
        button = rgba(0.169, 0.188, 0.255), border = rgba(0.300, 0.320, 0.400, 0.55), text = rgba(0.902, 0.922, 0.949),
        gold = rgba(0.890, 0.741, 0.400), tabSel = rgba(0.600, 0.470, 0.190), rowSel = rgba(0.215, 0.255, 0.360),
        muted = rgba(0.459, 0.490, 0.549), secondary = rgba(0.580, 0.612, 0.678), goGold = rgba(0.780, 0.620, 0.260),
        goText = rgba(0.075, 0.075, 0.095), ok = rgba(0.450, 0.780, 0.500), bad = rgba(0.900, 0.420, 0.400),
        dot = rgba(0.360, 0.560, 0.880), title = rgba(0.080, 0.090, 0.125), titleActive = rgba(0.110, 0.125, 0.175),
        rounding = { window = 6, child = 5, frame = 4, tab = 4 }, frameBorder = 1,
    },
    crimson = {
        window = rgba(0.090, 0.068, 0.074), panel = rgba(0.125, 0.090, 0.100), header = rgba(0.215, 0.110, 0.130),
        button = rgba(0.285, 0.130, 0.155), border = rgba(0.420, 0.220, 0.250, 0.60), text = rgba(0.930, 0.895, 0.885),
        gold = rgba(0.900, 0.620, 0.580), tabSel = rgba(0.500, 0.165, 0.205), rowSel = rgba(0.360, 0.140, 0.175),
        muted = rgba(0.560, 0.470, 0.480), secondary = rgba(0.700, 0.610, 0.610), goGold = rgba(0.640, 0.215, 0.255),
        goText = rgba(0.985, 0.935, 0.925), ok = rgba(0.560, 0.800, 0.520), bad = rgba(0.990, 0.520, 0.440),
        dot = rgba(0.820, 0.270, 0.370), title = rgba(0.250, 0.085, 0.105), titleActive = rgba(0.340, 0.115, 0.140),
        rounding = { window = 6, child = 5, frame = 4, tab = 4 }, frameBorder = 1,
    },
}
U.THEME_ORDER = { 'classic', 'squad', 'crimson' }
U.THEME_NAMES = { classic = 'Classic', squad = 'Squad', crimson = 'Crimson' }
U.DEFAULT = 'crimson'  -- for a new installation only (an existing one keeps what it has: see the add-ons' settings)

-- The added keys. on / onHi: a control that is switched on. warn: a state that needs the player ("Apply needed").
-- busy: a control that waits for the server. Classic and Crimson: made from that palette's own ok, gold and button.
-- Squad: the Squads menu's own colours, as they were before themes.
for _, name in ipairs({ 'classic', 'crimson' }) do
    local c = U.THEMES[name]
    c.on, c.onHi, c.warn, c.busy = times(c.ok, 0.55), times(c.ok, 0.70), c.gold, times(c.button, 0.80)
end
U.THEMES.squad.on, U.THEMES.squad.onHi = rgba(0.16, 0.48, 0.28), rgba(0.22, 0.60, 0.36)
U.THEMES.squad.warn, U.THEMES.squad.busy = rgba(0.96, 0.76, 0.36), rgba(0.22, 0.24, 0.28)

function U.valid(name)
    return type(name) == 'string' and U.THEMES[name] ~= nil
end

-- the palette and the name used (anything unknown: `fallback`, else the default)
function U.theme(name, fallback)
    if not U.valid(name) then
        name = U.valid(fallback) and fallback or U.DEFAULT
    end

    return U.THEMES[name], name
end

-- ---------------------------------------------------------------- scrollbars
-- (2026-11-25) a scrollbar in every window and panel of both add-ons, from the palette: the track a faint band of the
-- window colour, the grab the palette's button colour, brighter under the mouse, and the palette's accent (tabSel: Classic
-- gold-brown, Squad gold, Crimson red) while it is dragged. Before, only the Gambits grab was set and everything else was
-- ImGui's / Ashita's own (a red track and grab in the Squads menu whatever the theme).
function U.scrollbar_colors(c)
    return {
        { 'ImGuiCol_ScrollbarBg', { c.window[1], c.window[2], c.window[3], 0.55 } },
        { 'ImGuiCol_ScrollbarGrab', c.button },
        { 'ImGuiCol_ScrollbarGrabHovered', times(c.button, 1.45) },
        { 'ImGuiCol_ScrollbarGrabActive', c.tabSel },
    }
end

-- ---------------------------------------------------------------- one window's colours and metrics
-- (the Gambits window has pushed exactly this list since 0.3.1; the scrollbar entries follow it since 2026-11-25)
function U.window_colors(c)
    local list = {
        { 'ImGuiCol_WindowBg', c.window }, { 'ImGuiCol_ChildBg', c.panel }, { 'ImGuiCol_PopupBg', c.window },
        { 'ImGuiCol_Text', c.text }, { 'ImGuiCol_TextDisabled', c.muted }, { 'ImGuiCol_Border', c.border },
        { 'ImGuiCol_Separator', c.border }, { 'ImGuiCol_FrameBg', c.header },
        { 'ImGuiCol_FrameBgHovered', times(c.header, 1.25) }, { 'ImGuiCol_FrameBgActive', times(c.header, 1.40) },
        { 'ImGuiCol_Button', c.button }, { 'ImGuiCol_ButtonHovered', times(c.button, 1.25) },
        { 'ImGuiCol_ButtonActive', times(c.button, 1.40) }, { 'ImGuiCol_Header', c.header },
        { 'ImGuiCol_HeaderHovered', times(c.header, 1.25) }, { 'ImGuiCol_HeaderActive', times(c.header, 1.40) },
        { 'ImGuiCol_CheckMark', c.gold }, { 'ImGuiCol_SliderGrab', c.gold }, { 'ImGuiCol_ScrollbarGrab', c.button },
        { 'ImGuiCol_TitleBg', c.title or c.header }, { 'ImGuiCol_TitleBgActive', c.titleActive or c.header },
        { 'ImGuiCol_TitleBgCollapsed', c.title or c.header },
    }
    for _, item in ipairs(U.scrollbar_colors(c)) do
        if item[1] ~= 'ImGuiCol_ScrollbarGrab' then -- (the grab is in the list above already: the same value)
            list[#list + 1] = item
        end
    end

    return list
end

-- the shared metrics (the Gambits editor's): padding 8x8, frame 4x3, spacing 6x4, and the palette's own rounding
function U.window_vars(c, s)
    s = s or function(px) return px end
    local list = {
        { 'ImGuiStyleVar_WindowPadding', { s(8), s(8) } }, { 'ImGuiStyleVar_FramePadding', { s(4), s(3) } },
        { 'ImGuiStyleVar_ItemSpacing', { s(6), s(4) } }, { 'ImGuiStyleVar_ItemInnerSpacing', { s(4), s(4) } },
    }
    if c.rounding then
        list[#list + 1] = { 'ImGuiStyleVar_WindowRounding', s(c.rounding.window) }
        list[#list + 1] = { 'ImGuiStyleVar_ChildRounding', s(c.rounding.child) }
        list[#list + 1] = { 'ImGuiStyleVar_FrameRounding', s(c.rounding.frame) }
        list[#list + 1] = { 'ImGuiStyleVar_PopupRounding', s(c.rounding.frame) }
    end

    if c.frameBorder then
        list[#list + 1] = { 'ImGuiStyleVar_FrameBorderSize', c.frameBorder }
    end

    return list
end

-- ---------------------------------------------------------------- the Squads menu's colours per theme
-- Squad: every colour the menu, its button, the Profile and the Spells window used before themes, value for value.
-- Classic and Crimson: the same roles filled from the palette.
local MENU_SQUAD = {
    c = {
        gold = rgba(0.89, 0.74, 0.40), text = rgba(0.88, 0.89, 0.92), dim = rgba(0.56, 0.59, 0.66), good = rgba(0.42, 0.85, 0.52),
        bad = rgba(0.95, 0.42, 0.40), warn = rgba(0.96, 0.76, 0.36), hp = rgba(0.30, 0.70, 0.38), mp = rgba(0.30, 0.50, 0.90),
        on = rgba(0.16, 0.48, 0.28), onHi = rgba(0.22, 0.60, 0.36), sel = rgba(0.55, 0.43, 0.18), selHi = rgba(0.68, 0.54, 0.24),
        panel = rgba(0.065, 0.075, 0.105, 0.97), line = rgba(0.30, 0.32, 0.40, 0.55), faint = rgba(0.46, 0.49, 0.55),
        busy = rgba(0.22, 0.24, 0.28), go = rgba(0.55, 0.43, 0.18), goHi = rgba(0.68, 0.54, 0.24), goText = rgba(0.88, 0.89, 0.92),
    },
    window = {
        { 'ImGuiCol_WindowBg', rgba(0.07, 0.08, 0.11, 0.96) }, { 'ImGuiCol_ChildBg', rgba(0.10, 0.11, 0.15, 0.80) },
        { 'ImGuiCol_Border', rgba(0.32, 0.34, 0.42, 0.55) }, { 'ImGuiCol_Button', rgba(0.17, 0.19, 0.25) },
        { 'ImGuiCol_ButtonHovered', rgba(0.25, 0.28, 0.37) }, { 'ImGuiCol_ButtonActive', rgba(0.30, 0.34, 0.45) },
        { 'ImGuiCol_FrameBg', rgba(0.14, 0.16, 0.21) }, { 'ImGuiCol_FrameBgHovered', rgba(0.20, 0.22, 0.29) },
        { 'ImGuiCol_CheckMark', rgba(0.89, 0.74, 0.40) }, { 'ImGuiCol_Header', rgba(0.20, 0.22, 0.29) },
        { 'ImGuiCol_HeaderHovered', rgba(0.26, 0.29, 0.38) }, { 'ImGuiCol_Separator', rgba(0.32, 0.34, 0.42, 0.55) },
        { 'ImGuiCol_Text', rgba(0.88, 0.89, 0.92) },
    },
    button = {
        { 'ImGuiCol_WindowBg', rgba(0.05, 0.06, 0.09, 0.70) }, { 'ImGuiCol_Border', rgba(0.89, 0.74, 0.40, 0.55) },
        { 'ImGuiCol_Button', rgba(0.13, 0.16, 0.26, 0.95) }, { 'ImGuiCol_ButtonHovered', rgba(0.22, 0.27, 0.42) },
        { 'ImGuiCol_ButtonActive', rgba(0.30, 0.36, 0.55) }, { 'ImGuiCol_Text', rgba(0.89, 0.74, 0.40) },
    },
}

local menuCache = {}
function U.menu(name)
    local c
    c, name = U.theme(name)
    if menuCache[name] then
        return menuCache[name]
    end

    local m
    if name == 'squad' then
        m = MENU_SQUAD
    else
        local function alpha(col, a) return { col[1], col[2], col[3], a } end
        m = {
            c = {
                gold = c.gold, text = c.text, dim = c.secondary, good = c.ok, bad = c.bad, warn = c.warn,
                hp = MENU_SQUAD.c.hp, mp = MENU_SQUAD.c.mp, -- (bar colours are data, the same in every theme)
                on = c.on, onHi = c.onHi, sel = c.tabSel, selHi = times(c.tabSel, 1.25),
                panel = alpha(c.window, 0.97), line = c.border, faint = c.muted, busy = c.busy,
                go = c.goGold, goHi = times(c.goGold, 1.15), goText = c.goText,
            },
            window = {
                { 'ImGuiCol_WindowBg', alpha(c.window, 0.96) }, { 'ImGuiCol_ChildBg', alpha(c.panel, 0.80) },
                { 'ImGuiCol_PopupBg', c.window }, { 'ImGuiCol_Border', c.border }, { 'ImGuiCol_Button', c.button },
                { 'ImGuiCol_ButtonHovered', times(c.button, 1.25) }, { 'ImGuiCol_ButtonActive', times(c.button, 1.40) },
                { 'ImGuiCol_FrameBg', c.header }, { 'ImGuiCol_FrameBgHovered', times(c.header, 1.25) },
                { 'ImGuiCol_CheckMark', c.gold }, { 'ImGuiCol_Header', c.header },
                { 'ImGuiCol_HeaderHovered', times(c.header, 1.25) }, { 'ImGuiCol_Separator', c.border },
                { 'ImGuiCol_Text', c.text },
            },
            button = {
                { 'ImGuiCol_WindowBg', alpha(c.window, 0.70) }, { 'ImGuiCol_Border', alpha(c.gold, 0.55) },
                { 'ImGuiCol_Button', alpha(c.button, 0.95) }, { 'ImGuiCol_ButtonHovered', times(c.button, 1.25) },
                { 'ImGuiCol_ButtonActive', times(c.button, 1.40) }, { 'ImGuiCol_Text', c.gold },
            },
        }
    end

    -- (polish) the windows have ImGui's own title bar now, like the Gambits window: its colours from the palette
    -- (title / titleActive, else header), and the row states (see U.states). Additions; nothing above is changed.
    if not m.titled then
        m.titled = true
        m.window[#m.window + 1] = { 'ImGuiCol_TitleBg', c.title or c.header }
        m.window[#m.window + 1] = { 'ImGuiCol_TitleBgActive', c.titleActive or c.header }
        m.window[#m.window + 1] = { 'ImGuiCol_TitleBgCollapsed', c.title or c.header }
        for _, item in ipairs(U.scrollbar_colors(c)) do -- (2026-11-25) the same scrollbars as the Gambits window
            m.window[#m.window + 1] = item
        end
        local st = U.states(c)
        m.c.rowFill, m.c.rowLine, m.c.hover = st.rowFill, st.rowLine, st.hover
    end

    m.name, m.palette = name, c
    menuCache[name] = m
    return m
end

-- ---------------------------------------------------------------- (polish) shared sizes and states
-- Sizes in pixels at 100 % (each add-on scales them its own way). tab: the main tabs of a window (Squad / Dualbox /
-- Auto, Stats / Gear). tabCompact: secondary choices and small controls (Equipment / Look, a rule's Up / Down).
-- Buttons, drop-downs and text fields keep ImGui's frame height (font + 2 x 3). group: the space between two groups
-- of rows, a little more than between two rows of one group (ItemSpacing 4).
U.SIZE = { tab = 24, tabCompact = 19, tabPad = 12, tabPadCompact = 7, group = 7, labelCol = 54 }

-- The states every window draws the same way, made from the palette's own values (no palette value is changed and
-- none is added to a palette):
--   tab / tabHi      a selected tab: the palette's tabSel (Crimson: its red)
--   rowFill, rowLine a selected row: a light tint of rowSel and a thin line of a brighter tabSel
--   hover            a row under the mouse
--   active           running / switched on: ok (green);  warn: needs the player (Apply needed);  muted: secondary
local stateCache = setmetatable({}, { __mode = 'k' })
function U.states(c)
    local st = stateCache[c]
    if st == nil then
        st = {
            tab = c.tabSel, tabHi = times(c.tabSel, 1.25),
            rowFill = { c.rowSel[1], c.rowSel[2], c.rowSel[3], 0.42 }, rowLine = times(c.tabSel, 1.45),
            hover = { c.rowSel[1], c.rowSel[2], c.rowSel[3], 0.22 },
            active = c.ok, warn = c.warn, muted = c.muted, secondary = c.secondary,
        }
        stateCache[c] = st
    end

    return st
end

-- a filled rectangle with a thin line around it, on the window's draw list (the frame of a selected row). fill or
-- line may be nil. Returns false when this ImGui cannot draw it (the caller's own highlight is then all there is).
function U.frame(g, x, y, w, h, fill, line, rounding)
    if not (g.GetWindowDrawList and g.ColorConvertFloat4ToU32) or w <= 0 or h <= 0 then
        return false
    end

    local okD, draw = pcall(g.GetWindowDrawList)
    if not okD or draw == nil then
        return false
    end

    local function u32(col)
        local ok, v = pcall(g.ColorConvertFloat4ToU32, col)
        return ok and v or nil
    end

    local done = false
    local f = fill and u32(fill)
    if f ~= nil then
        done = pcall(function() draw:AddRectFilled({ x, y }, { x + w, y + h }, f, rounding or 3) end) or done
    end

    local l = line and u32(line)
    if l ~= nil then
        -- four thin bars: AddRectFilled is in every binding this file has met, AddRect is not
        done = pcall(function()
            draw:AddRectFilled({ x, y }, { x + w, y + 1 }, l, 0)
            draw:AddRectFilled({ x, y + h - 1 }, { x + w, y + h }, l, 0)
            draw:AddRectFilled({ x, y }, { x + 1, y + h }, l, 0)
            draw:AddRectFilled({ x + w - 1, y }, { x + w, y + h }, l, 0)
        end) or done
    end

    return done
end

-- the line around the control that was drawn last (a selected row of a list). False when this ImGui cannot say where
-- that control is: the row then has its tint only.
function U.outline_item(g, line)
    if not (g.GetItemRectMin and g.GetItemRectMax) then
        return false
    end

    local function point(fn)
        local ok, a, b = pcall(fn)
        if not ok or a == nil then
            return nil
        end

        if type(a) == 'table' then
            return tonumber(a[1] or a.x), tonumber(a[2] or a.y)
        end

        return tonumber(a), tonumber(b)
    end

    local x1, y1 = point(g.GetItemRectMin)
    local x2, y2 = point(g.GetItemRectMax)
    if not (x1 and y1 and x2 and y2) then
        return false
    end

    return U.frame(g, x1, y1, x2 - x1, y2 - y1, nil, line, 0)
end

-- the screen position of the next control, or nil
function U.cursor(g)
    if not g.GetCursorScreenPos then
        return nil
    end

    local ok, a, b = pcall(g.GetCursorScreenPos)
    if not ok or a == nil then
        return nil
    end

    if type(a) == 'table' then
        local x, y = tonumber(a[1] or a.x), tonumber(a[2] or a.y)
        return x and y and { x, y } or nil
    end

    return (type(a) == 'number' and type(b) == 'number') and { a, b } or nil
end

-- A divider between two panels that can be dragged sideways: a thin button `w` x `h` pixels; while it is held, the
-- mouse's movement is added to `value` (kept between lo and hi). Returns the value and whether it is being dragged.
-- Only ImGui's own calls (IsItemActive, GetMouseDragDelta, ResetMouseDragDelta: the Squads button is dragged the same
-- way). Without them it is a plain gap and the value stays what it was.
function U.splitter(g, id, w, h, value, lo, hi, colors)
    local token = U.push(g, colors)
    local ok = pcall(g.Button, id, { w, h })
    U.pop(g, token)
    if not ok then
        return value, false
    end

    if g.IsItemHovered and g.SetMouseCursor and rawget(_G, 'ImGuiMouseCursor_ResizeEW') ~= nil then
        local okH, hot = pcall(g.IsItemHovered)
        if okH and hot then pcall(g.SetMouseCursor, rawget(_G, 'ImGuiMouseCursor_ResizeEW')) end
    end

    if not (g.IsItemActive and g.GetMouseDragDelta and g.ResetMouseDragDelta) then
        return value, false
    end

    local okA, active = pcall(g.IsItemActive)
    if not (okA and active) then
        return value, false
    end

    local okD, a, b = pcall(g.GetMouseDragDelta, 0, 0)
    local dx = okD and (type(a) == 'table' and tonumber(a[1] or a.x) or tonumber(a)) or nil
    if dx ~= nil and dx ~= 0 then
        value = value + dx
        pcall(g.ResetMouseDragDelta, 0)
    end

    return math.max(lo, math.min(hi, value)), true
end

-- ---------------------------------------------------------------- ImGui stacks that cannot be left unbalanced
local function G(name) return rawget(_G, name) end

-- pushes colours ({ { 'ImGuiCol_X', rgba }, ... }) and style vars; returns a token for U.pop
function U.push(g, colors, vars)
    local token = { colors = 0, vars = 0 }
    for _, item in ipairs(colors or {}) do
        local id = G(item[1])
        if id ~= nil and item[2] ~= nil and g.PushStyleColor then
            if pcall(g.PushStyleColor, id, item[2]) then token.colors = token.colors + 1 end
        end
    end

    if g.PushStyleVar then
        for _, item in ipairs(vars or {}) do
            local id = G(item[1])
            if id ~= nil and item[2] ~= nil then
                if pcall(g.PushStyleVar, id, item[2]) then token.vars = token.vars + 1 end
            end
        end
    end

    return token
end

function U.pop(g, token)
    if token.vars > 0 and g.PopStyleVar then pcall(g.PopStyleVar, token.vars) end
    if token.colors > 0 and g.PopStyleColor then pcall(g.PopStyleColor, token.colors) end
    token.vars, token.colors = 0, 0
end

-- push, run fn, pop exactly what was pushed (also when fn fails), then raise fn's error again
function U.with(g, colors, vars, fn, ...)
    local token = U.push(g, colors, vars)
    local ok, err = pcall(fn, ...)
    U.pop(g, token)
    if not ok then
        error(err, 0)
    end

    return err
end

-- ---------------------------------------------------------------- text that is never read as a printf format
-- Ashita hands the text of imgui.SetTooltip and imgui.TextWrapped to ImGui as a FORMAT: a '%' in an item description
-- ("Haste+4%") is read as a conversion and can end the game. TextUnformatted never formats.
U.TOOLTIP_WRAP_EM = 27

function U.format_safe(text)
    return (tostring(text or ''):gsub('%%', '%%%%'))
end

function U.tooltip(g, text, fallbackWidth)
    if text == nil or not (g.IsItemHovered and g.IsItemHovered()) then
        return false
    end

    if g.BeginTooltip and g.EndTooltip and g.TextUnformatted then
        if g.BeginTooltip() ~= false then
            local wrap = nil
            if g.PushTextWrapPos and g.PopTextWrapPos then
                local okS, size = pcall(function() return g.GetFontSize and g.GetFontSize() end)
                wrap = (okS and type(size) == 'number' and size > 0) and size * U.TOOLTIP_WRAP_EM or (fallbackWidth or 350)
                g.PushTextWrapPos(wrap)
            end

            pcall(g.TextUnformatted, tostring(text))
            if wrap then g.PopTextWrapPos() end
            g.EndTooltip()
        end
    elseif g.SetTooltip then
        g.SetTooltip(U.format_safe(text))
    end

    return true
end

-- text that wraps at the panel's edge, in a colour (nil: the window's text colour)
function U.wrapped(g, color, text)
    text = tostring(text or '')
    local token = U.push(g, color and { { 'ImGuiCol_Text', color } } or nil)
    if g.PushTextWrapPos and g.PopTextWrapPos and g.TextUnformatted then
        g.PushTextWrapPos(0)
        pcall(g.TextUnformatted, text)
        g.PopTextWrapPos()
    elseif g.TextWrapped then
        pcall(g.TextWrapped, U.format_safe(text))
    else
        pcall(g.Text, text)
    end

    U.pop(g, token)
end

-- the width and height left in the current window or panel; nil when this ImGui cannot tell
function U.avail(g)
    if g.GetContentRegionAvail then
        local ok, a, b = pcall(g.GetContentRegionAvail)
        if ok then
            if type(a) == 'table' then
                local w = tonumber(a[1] or a.x)
                if w ~= nil then
                    return w, tonumber(a[2] or a.y) or 0
                end
            elseif type(a) == 'number' then
                return a, tonumber(b) or 0
            end
        end
    end

    return nil, nil
end

-- continue the line when `w` pixels still fit, else start a new one (also when the line is already past the edge:
-- the width left is then 0 or less). Returns true when it stayed on the line.
function U.same_if_fits(g, w, spacing)
    g.SameLine(0, spacing or 6)
    local left = U.avail(g)
    if g.NewLine and left ~= nil and left < w then
        g.NewLine()
        return false
    end

    return true
end

-- ---------------------------------------------------------------- the shared theme choice of ONE character
-- config/addons/xiforever/<Name>_<ServerId>/ui.cfg holds "theme=<name>". It is written ONLY when the player picks a
-- theme; an add-on that merely loads never makes it. While it does not exist each add-on keeps its own saved look.
-- One file per character: two game windows (dualbox) never write the same file.
function U.identity(name, id)
    name = tostring(name or ''):gsub('%z', ''):match('^%s*(.-)%s*$') or ''
    id = tonumber(id) or 0
    if name == '' or id <= 0 then
        return nil
    end

    return (name:gsub('[^%w_]', '_')) .. '_' .. string.format('%d', id)
end

-- the character logged in in THIS game window, or nil at the title screen
function U.current_identity()
    local ok, name, id = pcall(function()
        local party = AshitaCore:GetMemoryManager():GetParty()
        return party:GetMemberName(0), party:GetMemberServerId(0)
    end)
    if not ok then
        return nil
    end

    return U.identity(name, id)
end

function U.pref_dir(install, identity)
    if type(install) ~= 'string' or install == '' or identity == nil then
        return nil
    end

    if not install:match('[/\\]$') then
        install = install .. '/'
    end

    return install .. 'config/addons/xiforever/' .. identity .. '/'
end

function U.pref_path(install, identity)
    local dir = U.pref_dir(install, identity)
    return dir and (dir .. 'ui.cfg') or nil
end

-- the chosen theme in that file, or nil (no file, no theme line, an unknown name: nothing is chosen)
function U.read_pref(path)
    local f = path and io.open(path, 'r')
    if not f then
        return nil
    end

    local found = nil
    for line in f:lines() do
        local k, v = line:match('^%s*([%w_]+)%s*=%s*(.-)%s*$')
        if k == 'theme' and U.valid(v) then
            found = v
        end
    end

    f:close()
    return found
end

-- writes the choice (a temporary file, then renamed over the old one). mkdir(dir) makes one folder if it is missing.
function U.write_pref(install, identity, theme, mkdir)
    local dir = U.pref_dir(install, identity)
    if dir == nil or not U.valid(theme) then
        return false
    end

    if mkdir then
        local parent = dir:gsub('[^/\\]+[/\\]$', '')
        pcall(mkdir, parent)
        pcall(mkdir, dir)
    end

    local path, tmp = dir .. 'ui.cfg', dir .. 'ui.cfg.tmp'
    local f = io.open(tmp, 'w')
    if not f then
        return false
    end

    f:write('theme=' .. theme .. '\n')
    f:close()
    os.remove(path)
    if not os.rename(tmp, path) then
        os.remove(tmp)
        return false
    end

    return true
end

-- The "Gambits is loaded" mark (config/addons/xiforever/<Name>_<ServerId>/gambits.loaded, written by Gambits, read by
-- the Squads menu). Both add-ons run inside the same game process, so the mark carries that process's id: one that a
-- crashed game left behind names another process and counts as absent. Where the id cannot be read (no LuaJIT ffi)
-- the mark is taken as it is.
function U.process_id()
    if U.pid == nil then
        U.pid = false
        local ok, ffi = pcall(require, 'ffi')
        if ok and type(ffi) == 'table' then
            pcall(ffi.cdef, 'unsigned long GetCurrentProcessId(void);')
            local got, value = pcall(function() return tonumber(ffi.C.GetCurrentProcessId()) end)
            if got and value and value > 0 then
                U.pid = value
            end
        end
    end

    return U.pid or nil
end

function U.presence_text(version)
    local pid = U.process_id()
    return 'Gambits ' .. tostring(version or '') .. '\n' .. (pid and ('pid=' .. string.format('%d', pid) .. '\n') or '')
end

function U.presence_valid(path)
    local f = path and io.open(path, 'r')
    if not f then
        return false
    end

    local text = f:read('*a') or ''
    f:close()
    local pid, mine = tonumber(text:match('pid=(%d+)')), U.process_id()
    return pid == nil or mine == nil or pid == mine
end

-- A small follower for one add-on: U.follow.new(install) -> f; f:poll(now) returns the theme chosen for the character
-- logged in now (nil: none chosen, use your own), reading the file at most once a second and again at once when the
-- character changes; f:pick(theme, mkdir) writes the player's choice for that character.
U.follow = {}
U.follow.__index = U.follow

function U.follow.new(install, identityFn)
    return setmetatable({ install = install, identityFn = identityFn or U.current_identity, at = -1000, id = false, theme = nil }, U.follow)
end

-- The game can report no character for a moment while a character is logged in (no name or server id yet while a
-- zone loads). That is not a logout: for U.GRACE seconds the character stays the one it was, with the theme that was
-- read for it, and no file is looked at. After that it is a logout. Another character is another character at once.
-- (Preventive: whether the game really reports none during a zone change was not seen in the game.)
U.GRACE = 30

function U.follow:poll(now, force)
    local id = self.identityFn()
    if id == nil and self.id then
        self.goneAt = self.goneAt or now
        if now - self.goneAt < U.GRACE then
            return self.theme, self.id
        end
    else
        self.goneAt = nil
    end

    if id ~= self.id then
        self.id, self.theme, force = id, nil, true -- (another character, or logged out: never the previous one's choice)
    end

    if force or now - self.at >= 1.0 then
        self.at = now
        self.theme = id and U.read_pref(U.pref_path(self.install, id)) or nil
    end

    return self.theme, self.id
end

-- a logout that the add-on knows of for sure (Gambits: its settings library says so): no waiting
function U.follow:reset()
    self.id, self.theme, self.goneAt, self.at = false, nil, nil, -1000
end

function U.follow:pick(theme, mkdir)
    local id = self.identityFn()
    if id == nil or not U.valid(theme) then
        return false -- (not logged in: there is no character to remember it for)
    end

    local ok = U.write_pref(self.install, id, theme, mkdir)
    if ok then
        self.id, self.theme = id, theme
    end

    return ok
end

return U

--[[ Crystal Boy: libretro core binding (LuaJIT FFI, Lua 5.1 syntax).
     Loads one core DLL, runs it frame by frame, and keeps the newest picture
     in a staging buffer. Callbacks from C into Lua are only called from inside
     core calls, which are kept out of JIT traces (see jit.off below). ]]
local ffi = require('ffi')

ffi.cdef[[
typedef bool     (*retro_environment_t)(unsigned cmd, void *data);
typedef void     (*retro_video_refresh_t)(const void *data, unsigned width, unsigned height, size_t pitch);
typedef void     (*retro_audio_sample_t)(int16_t left, int16_t right);
typedef size_t   (*retro_audio_sample_batch_t)(const int16_t *data, size_t frames);
typedef void     (*retro_input_poll_t)(void);
typedef int16_t  (*retro_input_state_t)(unsigned port, unsigned device, unsigned index, unsigned id);

struct retro_game_info { const char *path; const void *data; size_t size; const char *meta; };
struct retro_system_info { const char *library_name; const char *library_version; const char *valid_extensions; bool need_fullpath; bool block_extract; };
struct retro_game_geometry { unsigned base_width; unsigned base_height; unsigned max_width; unsigned max_height; float aspect_ratio; };
struct retro_system_timing { double fps; double sample_rate; };
struct retro_system_av_info { struct retro_game_geometry geometry; struct retro_system_timing timing; };
struct retro_variable { const char *key; const char *value; };

void     retro_set_environment(retro_environment_t);
void     retro_set_video_refresh(retro_video_refresh_t);
void     retro_set_audio_sample(retro_audio_sample_t);
void     retro_set_audio_sample_batch(retro_audio_sample_batch_t);
void     retro_set_input_poll(retro_input_poll_t);
void     retro_set_input_state(retro_input_state_t);
void     retro_init(void);
void     retro_deinit(void);
unsigned retro_api_version(void);
void     retro_get_system_info(struct retro_system_info *info);
void     retro_get_system_av_info(struct retro_system_av_info *info);
void     retro_reset(void);
void     retro_run(void);
size_t   retro_serialize_size(void);
bool     retro_serialize(void *data, size_t size);
bool     retro_unserialize(const void *data, size_t size);
bool     retro_load_game(const struct retro_game_info *game);
void     retro_unload_game(void);
void    *retro_get_memory_data(unsigned id);
size_t   retro_get_memory_size(unsigned id);
]]

local M = {}

M.FMT_0RGB1555, M.FMT_XRGB8888, M.FMT_RGB565 = 0, 1, 2
M.MEM_SAVE, M.MEM_SYSTEM = 0, 2
-- joypad ids
M.B, M.Y, M.SELECT, M.START, M.UP, M.DOWN, M.LEFT, M.RIGHT, M.A = 0, 1, 2, 3, 4, 5, 6, 7, 8

local core      -- ffi library
local cbs = {}  -- callbacks kept alive
local keep = {} -- strings/buffers the core may hold pointers to
local st = {}   -- state

M.pressed = {}  -- [joypad id] = true while held
M.log = function(msg) end

-- NULL test that works in LuaJIT and in other FFI implementations.
local function null(p) return p == nil or tonumber(ffi.cast('uintptr_t', p)) == 0 end

local function bpp(fmt) return fmt == M.FMT_XRGB8888 and 4 or 2 end

local function env(cmd, data)
    if M.trace then M.trace('env ' .. tostring(cmd), 'env' .. tostring(cmd), 2) end
    cmd = cmd % 0x10000 -- drop the EXPERIMENTAL flag
    if cmd == 3 then -- GET_CAN_DUPE
        ffi.cast('bool *', data)[0] = true
        return true
    elseif cmd == 10 then -- SET_PIXEL_FORMAT
        local f = ffi.cast('int *', data)[0]
        if f == 0 or f == 1 or f == 2 then st.fmt = f; return true end
        return false
    elseif cmd == 9 or cmd == 31 then -- system / save directory
        if not st.dir_c or null(data) then return false end
        ffi.cast('const char **', data)[0] = st.dir_c
        return true
    elseif cmd == 52 then -- GET_CORE_OPTIONS_VERSION: 0 = plain variables
        ffi.cast('unsigned *', data)[0] = 0
        return true
    elseif cmd == 15 then -- GET_VARIABLE
        local v = ffi.cast('struct retro_variable *', data)
        local key = not null(v.key) and ffi.string(v.key) or ''
        local val = st.vars and st.vars[key]
        if val then
            local s = ffi.new('char[?]', #val + 1, val)
            keep['var_' .. key] = s
            v.value = s
            return true
        end
        v.value = nil
        return false
    elseif cmd == 17 then -- GET_VARIABLE_UPDATE
        ffi.cast('bool *', data)[0] = false
        return true
    end
    return false
end

local function video(data, w, h, pitch)
    if M.trace then M.trace('video ' .. tostring(w) .. 'x' .. tostring(h) .. ' pitch ' .. tostring(pitch) .. ' fmt ' .. tostring(st.fmt), 'video', 3) end
    if null(data) then st.dup = true; return end -- frame duplicated
    local b = bpp(st.fmt)
    local row = w * b
    if w > 256 or h > 256 then return end
    for y = 0, h - 1 do
        ffi.copy(st.frame + y * row, ffi.cast('const uint8_t *', data) + y * pitch, row)
    end
    st.fw, st.fh, st.frow = w, h, row
    st.frames_drawn = st.frames_drawn + 1
end

local function input_state(port, device, index, id)
    if port == 0 and device == 1 and M.pressed[id] then return 1 end
    return 0
end

-- Sound (1.5): the core's samples are collected here while it runs and handed to cb/audio.lua after the frame
-- (M.audio_take). Stereo int16 frames; when nobody takes them the oldest are simply overwritten from the start.
local AUDIO_CAP = 8192
local function audio_batch(data, frames)
    local n = tonumber(frames)
    if st.audio and n > 0 and not null(data) then
        local room = AUDIO_CAP - st.audio_n
        local take = n < room and n or room
        if take > 0 then
            ffi.copy(st.audio + st.audio_n * 2, data, take * 4)
            st.audio_n = st.audio_n + take
        end
    end
    return frames
end
local function audio_one(l, r)
    if st.audio and st.audio_n < AUDIO_CAP then
        st.audio[st.audio_n * 2], st.audio[st.audio_n * 2 + 1] = l, r
        st.audio_n = st.audio_n + 1
    end
end
local function poll() end

-- Core calls that may call back into Lua must not be JIT-compiled.
local function c_run(n) for i = 1, n do core.retro_run() end end
local function c_load(info) return core.retro_load_game(info) end
local function c_init() core.retro_init() end
local function c_ser(buf, n) return core.retro_serialize(buf, n) end
local function c_unser(buf, n) return core.retro_unserialize(buf, n) end
local function c_reset() core.retro_reset() end
local function c_unload() core.retro_unload_game() end
if jit and jit.off then
    for _, f in ipairs({ c_run, c_load, c_init, c_ser, c_unser, c_reset, c_unload }) do jit.off(f, true) end
end

--- Open a core DLL. dir = folder the core may use for system/save files.
function M.open(path, dir, vars)
    if core then return true end
    local ok, lib = pcall(ffi.load, path)
    if not ok then return false, 'could not load core: ' .. tostring(lib) end
    local ok2, ver = pcall(function() return lib.retro_api_version() end)
    if not ok2 then return false, 'not a libretro core: ' .. tostring(ver) end
    if ver ~= 1 then return false, 'unsupported libretro version ' .. tostring(ver) end
    core = lib
    st = { fmt = M.FMT_0RGB1555, frames_drawn = 0, vars = vars or {} }
    st.frame = ffi.new('uint8_t[?]', 256 * 256 * 4)
    st.audio, st.audio_n = ffi.new('int16_t[?]', AUDIO_CAP * 2), 0
    if dir then st.dir_c = ffi.new('char[?]', #dir + 1, dir) end
    cbs.env   = ffi.cast('retro_environment_t', env)
    cbs.video = ffi.cast('retro_video_refresh_t', video)
    cbs.one   = ffi.cast('retro_audio_sample_t', audio_one)
    cbs.batch = ffi.cast('retro_audio_sample_batch_t', audio_batch)
    cbs.poll  = ffi.cast('retro_input_poll_t', poll)
    cbs.input = ffi.cast('retro_input_state_t', input_state)
    core.retro_set_environment(cbs.env)
    core.retro_set_video_refresh(cbs.video)
    core.retro_set_audio_sample(cbs.one)
    core.retro_set_audio_sample_batch(cbs.batch)
    core.retro_set_input_poll(cbs.poll)
    core.retro_set_input_state(cbs.input)
    c_init()
    local si = ffi.new('struct retro_system_info')
    core.retro_get_system_info(si)
    st.name = not null(si.library_name) and ffi.string(si.library_name) or 'core'
    st.need_fullpath = si.need_fullpath
    return true
end

function M.is_open() return core ~= nil end
function M.core_name() return st.name end
function M.loaded() return st.loaded == true end

--- Load ROM bytes (Lua string). path is passed along for cores that want it.
function M.load_game(rom, path)
    if not core then return false, 'no core' end
    if st.loaded then M.unload_game() end
    local buf = ffi.new('uint8_t[?]', #rom)
    ffi.copy(buf, rom, #rom)
    local p = ffi.new('char[?]', #path + 1, path)
    keep.rom, keep.rom_path = buf, p
    local info = ffi.new('struct retro_game_info')
    info.path, info.data, info.size, info.meta = p, buf, #rom, nil
    if not c_load(info) then return false, 'the core refused this ROM' end
    local av = ffi.new('struct retro_system_av_info')
    core.retro_get_system_av_info(av)
    st.fps = (av.timing.fps > 1) and av.timing.fps or 59.7275
    st.sample_rate = (av.timing.sample_rate > 1000) and math.floor(av.timing.sample_rate + 0.5) or 32768
    st.audio_n = 0
    st.loaded = true
    st.frames_drawn = 0
    return true
end

function M.unload_game()
    if core and st.loaded then c_unload() end
    st.loaded = false
    keep.rom = nil
end

function M.fps() return st.fps or 59.7275 end
function M.sample_rate() return st.sample_rate or 32768 end

--- The sound collected since the last call: pointer to stereo int16 frames, and how many. Empties the collection.
function M.audio_take()
    local n = st.audio_n or 0
    st.audio_n = 0
    return st.audio, n
end
function M.run(n) if core and st.loaded and n > 0 then c_run(n) end end
function M.reset() if core and st.loaded then c_reset() end end

--- Newest picture: pointer, width, height, bytes per row, pixel format, counter.
function M.frame() return st.frame, st.fw or 0, st.fh or 0, st.frow or 0, st.fmt, st.frames_drawn or 0 end

--- Battery memory (or system RAM) as a Lua string, nil if the game has none.
function M.memory(id)
    if not (core and st.loaded) then return nil end
    local n = tonumber(core.retro_get_memory_size(id or 0))
    local p = core.retro_get_memory_data(id or 0)
    if n == 0 or null(p) then return nil end
    return ffi.string(p, n)
end

--- Put saved bytes back into battery memory. Returns true if it fit.
function M.set_memory(id, bytes)
    if not (core and st.loaded) then return false end
    local n = tonumber(core.retro_get_memory_size(id))
    local p = core.retro_get_memory_data(id)
    if n == 0 or null(p) then return false end
    ffi.fill(p, n, 0)
    ffi.copy(p, bytes, math.min(n, #bytes))
    return #bytes <= n
end

function M.save_state()
    if not (core and st.loaded) then return nil, 'no game' end
    local n = tonumber(core.retro_serialize_size())
    if n == 0 then return nil, 'this core cannot save states' end
    local buf = ffi.new('uint8_t[?]', n)
    if not c_ser(buf, n) then return nil, 'the core could not save a state' end
    return ffi.string(buf, n)
end

function M.load_state(data)
    if not (core and st.loaded) then return false, 'no game' end
    local buf = ffi.new('uint8_t[?]', #data)
    ffi.copy(buf, data, #data)
    if not c_unser(buf, #data) then return false, 'the state does not fit this game' end
    return true
end

local function c_deinit() core.retro_deinit() end
if jit and jit.off then jit.off(c_deinit, true) end

--- Stop the game and shut the core down (called when the addon unloads).
function M.close()
    if not core then return end
    M.unload_game()
    c_deinit()
    core = nil
end

return M

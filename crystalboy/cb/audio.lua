--[[ Crystal Boy: sound (LuaJIT FFI, Windows waveOut; also what Wine / Proton provide).
     The emulator hands over its samples while it runs a frame; after the frame they are queued on the sound device in
     small blocks. Everything happens on the game's own thread: the device is opened without a callback and finished
     blocks are found by looking at their flags, so Windows never calls into Lua. Every call is wrapped by the caller in
     pcall, and any failure here simply leaves the Crystal Boy silent. ]]
local ffi = require('ffi')

ffi.cdef[[
typedef struct { uint16_t wFormatTag; uint16_t nChannels; uint32_t nSamplesPerSec; uint32_t nAvgBytesPerSec;
                 uint16_t nBlockAlign; uint16_t wBitsPerSample; uint16_t cbSize; } CB_WAVEFORMATEX;
typedef struct { char *lpData; uint32_t dwBufferLength; uint32_t dwBytesRecorded; uintptr_t dwUser; uint32_t dwFlags;
                 uint32_t dwLoops; void *lpNext; uintptr_t reserved; } CB_WAVEHDR;
uint32_t __stdcall waveOutOpen(void **phwo, uint32_t device, const CB_WAVEFORMATEX *format, uintptr_t callback, uintptr_t instance, uint32_t flags);
uint32_t __stdcall waveOutPrepareHeader(void *hwo, CB_WAVEHDR *hdr, uint32_t size);
uint32_t __stdcall waveOutUnprepareHeader(void *hwo, CB_WAVEHDR *hdr, uint32_t size);
uint32_t __stdcall waveOutWrite(void *hwo, CB_WAVEHDR *hdr, uint32_t size);
uint32_t __stdcall waveOutReset(void *hwo);
uint32_t __stdcall waveOutClose(void *hwo);
]]

local M = {}

local BLOCKS       = 12     -- blocks in the ring
local BLOCK_FRAMES = 2048   -- stereo frames one block can hold
local MAX_QUEUED   = 5      -- blocks waiting on the device at most (more = the sound would lag behind the picture)
local WHDR_PREPARED, WHDR_INQUEUE = 0x02, 0x10
local WAVE_MAPPER = 0xFFFFFFFF

local winmm, dev, hdrs, bufs, rate
local hdr_size = ffi.sizeof('CB_WAVEHDR')

function M.is_open() return dev ~= nil end
function M.rate() return rate end

--- Open the default sound device for 16-bit stereo at this sample rate. Returns true, or false and why.
function M.open(sample_rate)
    if dev then
        if rate == sample_rate then return true end
        M.close()
    end
    if not winmm then
        local ok, lib = pcall(ffi.load, 'winmm')
        if not ok then return false, 'winmm could not be loaded' end
        winmm = lib
    end
    local fmt = ffi.new('CB_WAVEFORMATEX')
    fmt.wFormatTag, fmt.nChannels, fmt.nSamplesPerSec = 1, 2, sample_rate
    fmt.wBitsPerSample, fmt.nBlockAlign, fmt.nAvgBytesPerSec, fmt.cbSize = 16, 4, sample_rate * 4, 0
    local out = ffi.new('void *[1]')
    local err = winmm.waveOutOpen(out, WAVE_MAPPER, fmt, 0, 0, 0)
    if err ~= 0 or out[0] == nil then return false, 'the sound device did not open (code ' .. tostring(err) .. ')' end
    dev, rate = out[0], sample_rate
    hdrs = ffi.new('CB_WAVEHDR[?]', BLOCKS)
    bufs = {}
    for i = 0, BLOCKS - 1 do
        bufs[i] = ffi.new('int16_t[?]', BLOCK_FRAMES * 2)
        hdrs[i].lpData = ffi.cast('char *', bufs[i])
        hdrs[i].dwBufferLength = BLOCK_FRAMES * 4
        hdrs[i].dwFlags = 0
        winmm.waveOutPrepareHeader(dev, hdrs + i, hdr_size)
    end
    return true
end

--- Queue stereo frames (int16 pairs at `data`). volume 0..100. Returns how many frames were queued (0 = dropped).
function M.write(data, frames, volume)
    if not dev or frames <= 0 then return 0 end
    local queued, free = 0, nil
    for i = 0, BLOCKS - 1 do
        if bit.band(hdrs[i].dwFlags, WHDR_INQUEUE) ~= 0 then
            queued = queued + 1
        elseif free == nil and bit.band(hdrs[i].dwFlags, WHDR_PREPARED) ~= 0 then
            free = i
        end
    end
    if free == nil or queued >= MAX_QUEUED then return 0 end -- behind: let this bit of sound go
    if frames > BLOCK_FRAMES then
        data = data + (frames - BLOCK_FRAMES) * 2 -- keep the newest part
        frames = BLOCK_FRAMES
    end
    local dst, n = bufs[free], frames * 2
    if volume >= 100 then
        ffi.copy(dst, data, n * 2)
    else
        local v = math.max(0, volume) / 100
        v = v * v -- (hearing is not linear: 50 should sound about half as loud)
        for i = 0, n - 1 do dst[i] = data[i] * v end
    end
    hdrs[free].dwBufferLength = frames * 4
    if winmm.waveOutWrite(dev, hdrs + free, hdr_size) ~= 0 then return 0 end
    return frames
end

--- Drop whatever is still queued (pause, stop, a state was loaded).
function M.flush()
    if dev then winmm.waveOutReset(dev) end
end

function M.close()
    if not dev then return end
    winmm.waveOutReset(dev)
    for i = 0, BLOCKS - 1 do winmm.waveOutUnprepareHeader(dev, hdrs + i, hdr_size) end
    winmm.waveOutClose(dev)
    dev, hdrs, bufs, rate = nil, nil, nil, nil
end

return M

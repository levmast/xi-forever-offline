-- Crystal Boy completion rules.
-- One entry per game, keyed by the ROM's internal title (shown by /cb list).
-- A game counts as finished when its conditions match the game's memory:
--   memory = 'save'  the battery save (the same bytes as the .sav file)
--   memory = 'ram'   the Game Boy's work RAM while the game runs
-- Conditions (offsets start at 0):
--   { at = 0x1A0, equals = 3 }            byte equals a value
--   { at = 0x1A0, mask = 0x0F, equals = 3 } compare only some bits
--   { at = 0x10, size = 2, min = 500 }     2- or 4-byte numbers (little endian)
--   { at = 0x20, bits_set = 0x80 }  { at = 0x20, bits_clear = 0x01 }  { at = 5, nonzero = true }
-- Use all = { ... } (every condition) or any = { ... } (at least one).
-- Or, for games whose ending cannot be measured: playtime_hours = 10  (finished after that much real play).
-- Either one is enough. An entry with neither never counts as finished.
--
-- Finding the right bytes: shortly before the ending, type  /cb snap before
-- then finish the game and save, and type  /cb snap after  and  /cb diff before after
-- The changed bytes are listed in chat and in config\addons\crystalboy\snaps.

return {
    ['SEIKEN DENSETSU'] = {
        name = 'Final Fantasy Adventure',
        playtime_hours = 10,   -- a first playthrough is about 10 hours
        memory = 'ram',
        all = {
            -- the ending bytes, if they are ever measured (/cb record during the ending)
        },
    },
    ['SAGA']     = { name = 'Final Fantasy Legend',     playtime_hours = 8 },
    ['SAGA2 DX'] = { name = 'Final Fantasy Legend II',  playtime_hours = 12 },
    ['SAGA2']    = { name = 'Final Fantasy Legend II',  playtime_hours = 12 },
    ['SAGA3 DX'] = { name = 'Final Fantasy Legend III', playtime_hours = 15 },
    ['SAGA3']    = { name = 'Final Fantasy Legend III', playtime_hours = 15 },

    -- The free games that come with XI: Forever Offline (crystalboy-games\CREDITS.md). Times are a first playthrough.
    ['JUENO LEG 1JUNO'] = { name = 'Legend of Jueno',   playtime_hours = 9 },
    ['JUENO LEG 2JUNO'] = { name = 'Legend of Jueno 2', playtime_hours = 14 },
    ['JUENO LEG 3JUNO'] = { name = 'Legend of Jueno 3', playtime_hours = 13 },
    ['JUENO LEG 4JUNO'] = { name = 'Legend of Jueno 4', playtime_hours = 7 },

    -- Horro's Visit (the Dragon Quest X event): same treatment, one entry per part.
    ['DRAGONLAND 1'] = { name = 'Dragonland I',   playtime_hours = 8 },
    ['DRAGONLAND 2'] = { name = 'Dragonland II',  playtime_hours = 8 },
    ['DRAGONLAND 3'] = { name = 'Dragonland III', playtime_hours = 8 },
    ['DRAGONLAND 4'] = { name = 'Dragonland IV',  playtime_hours = 8 },
    ['DRAGONLAND 5'] = { name = 'Dragonland V',   playtime_hours = 8 },
}

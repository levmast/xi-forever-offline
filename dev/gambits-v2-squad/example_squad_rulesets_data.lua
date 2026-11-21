-- Example Rule Set store for Gambits v2, milestone 1 (server side). For a DEVELOPMENT server only.
-- Copy it to <dev server>/modules/custom/lua/squad_rulesets_data.lua, then in game:
--   !squad ruleset                 lists the sets
--   !squad ruleset <slot> 1        a WHM mate in that slot follows set 1 (Apply now / call it again)
--   !squad ruleset <slot> off      back to its WHM job rules
-- The file is re-read every time a mate is called. Checked by test_squad_rulesets.lua.
return {
    format  = 'xifo-ruleset-store',
    version = 1,
    sets    =
    {
        {
            format   = 'xifo-ruleset',
            version  = 1,
            num      = 1,
            id       = 'custom.whm.cure-basics',
            name     = 'WHM - Cure basics',
            job      = 'WHM',
            readonly = false,
            rules    =
            {
                { id = 'r1', on = true, target = 'PARTY', cond = { 'HPP_LT', 40 }, action = { 'family', 'CURE' } },
                { id = 'r2', on = true, target = 'PARTY', cond = { 'HPP_LT', 75 }, action = { 'spell', 'CURE_II' } },
            },
        },
    },
}

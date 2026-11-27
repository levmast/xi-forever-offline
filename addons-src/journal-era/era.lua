-- The era this server has: the base game, Rise of the Zilart,
-- Chains of Promathia and Treasures of Aht Urhgan.
--
-- Everything added after ToAU (Wings of the Goddess, the add-on
-- scenarios, Abyssea, Seekers of Adoulin, Rhapsodies of Vana'diel and
-- The Voracious Resurgence) is hidden from the Journal. Edit the two
-- tables below to change what counts as in-era.

local M = {}

local mission_areas = {
    bastok = true,
    windurst = true,
    sandoria = true,
    zilart = true,
    cop = true,
    toau = true,
    assault = true, -- Treasures of Aht Urhgan
}

local quest_categories = {
    sandoria = true,
    bastok = true,
    windurst = true,
    jeuno = true,
    outlands = true,
    other = true,
    whitegate = true, -- Treasures of Aht Urhgan
}

function M.FilterMissions(source)
    local result = {}

    for area, mission_list in pairs(source or {}) do
        if mission_areas[area] then
            result[area] = mission_list
        end
    end

    return result
end

-- Quests added after ToAU that sit in old-area categories in the data.
-- The Trial-Size avatar quests and Waking the Beast are not here: they
-- are 2006 or earlier.
local late_quests = {
    -- (2026-11-26, seraphinaspears) starts only after Seeing Spots, a Wings of the Goddess quest
    sdz_ss_atelloune_lament = true,
    bsz_pb_trust_bastok = true,
    wq_wd_trust_windurst = true,

    out_kaz_elshimo_list = true,
    out_nrg_border_crossing = true,
    out_nrg_li_telor_variant = true,
    out_nrg_skyward_ho = true,
    out_rab_detour_to_zepwell = true,
    oth_tvs_vw_op_026 = true,
    oth_riv_vw_op_004 = true,

    oth_pas_monstrosity = true,
    oth_xar_survival_of_wisest = true,
    oth_mul_records_of_eminence = true,
    oth_mul_unity_concord = true,
}

function M.FilterQuests(source)
    local result = {}

    for category, quest_list in pairs(source or {}) do
        if quest_categories[category] then
            local filtered = {}

            for _, quest in ipairs(quest_list) do
                if type(quest) == 'table'
                    and (quest.id == nil or not late_quests[quest.id]) then

                    filtered[#filtered + 1] = quest
                end
            end

            result[category] = filtered
        end
    end

    return result
end

function M.FilterMissionAreas(list)
    local result = {}

    for _, area in ipairs(list or {}) do
        if mission_areas[area] then
            result[#result + 1] = area
        end
    end

    return result
end

return M

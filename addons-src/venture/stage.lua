--[[
venture/stage - the Ventures pixel scene, the same one the XIFO app plays (xifo-app/src/ventures/Stage.tsx, ported
line for line): a camp's backdrop, the party on the left, the monster on the right, played back from the venture's
timeline. Phases: on the road (walking in), fighting (attacks in turn, the monster flinches, damage numbers, its HP
running down to the next kill), resting (sitting, "Z z"), home (victory pose).

Everything is placed on the app's 240 x 126 grid and drawn `P` screen pixels to a grid pixel. Positions, frames and
timings are the app's own; when one changes there, change it here.

    local Stage = dofile(path .. 'stage.lua')(gfx, art, assets)
    Stage.draw(x, y, P, { camps, events, sec, over, mates, party, still, label, tick })
]]
return function(gfx, ART, ASSETS)
    local S = {};

    local SCENE_W, SCENE_H = 240, 126;
    S.W, S.H = SCENE_W, SCENE_H;
    local JOBS = { 'WAR', 'MNK', 'WHM', 'BLM', 'RDM', 'THF', 'PLD', 'DRK', 'BST', 'BRD', 'RNG', 'SAM', 'NIN', 'DRG', 'SMN', 'BLU', 'COR', 'PUP' };
    S.JOBS = JOBS;
    local function set(list) local t = {}; for _, v in ipairs(list) do t[v] = true; end return t; end
    local CASTERS = set({ 'WHM', 'BLM', 'RDM', 'SMN', 'BRD', 'SCH', 'GEO' });
    local THRUST = set({ 'MNK', 'DRG', 'PUP', 'BST' });
    local SHOOT = set({ 'RNG', 'COR' });
    -- feet positions (grid x centre, y), front of the party first
    local SPOTS = { { 104, 108 }, { 84, 118 }, { 70, 100 }, { 52, 113 }, { 36, 103 }, { 20, 119 } };
    local MOB_AT = { 182, 112 };
    -- the light of the Vana'diel hour outdoors; caves, towers and halls keep their own light
    local INDOOR = set({ 'korroloka', 'gusgen', 'oztroja', 'ssg', 'crawlers', 'garlaige', 'gustav', 'onzozo', 'kuftal', 'krt', 'boyahda',
        'ifrits', 'den', 'aydeewa' });
    local TINT = {
        dawn = { 'rgba(120,70,160,0.22)', 'rgba(255,150,90,0.18)' },
        dusk = { 'rgba(110,40,120,0.28)', 'rgba(255,110,60,0.22)' },
        night = { 'rgba(6,10,40,0.38)', 'rgba(10,20,64,0.26)' },
    };
    local CAMPFIRE = { 64, 116 };
    local MOB_SCALE, MOBT_SCALE = 1.35, 1.1;
    -- the old 10 poses (the party's sprites have exactly these frames)
    local FRAME = { idle0 = 0, idle1 = 1, walk0 = 2, walk1 = 3, atk0 = 4, atk1 = 5, cast = 6, hurt = 7, sit = 8, win = 9 };
    -- a squad mate's 22 frames (the app's MATE_POSE) and the 12 of its sheet (GEN_POSE)
    local MATE_POSE = { idle = { 0, 1, 2 }, walk = { 3, 4, 5 }, swing = { 6, 7, 8 }, thrust = { 9, 10, 11 }, shoot = { 12, 13, 14 },
        cast = { 15, 16 }, hurt = { 17 }, evade = { 18 }, sit = { 19 }, win = { 20, 21 } };
    local GEN_POSE = { idle = { 0, 1, 2 }, walk = { 3, 4, 5 }, attack = { 6, 7, 8 }, ability = { 9, 10 }, hurt = { 11 } };
    -- race number -> how tall that race stands next to a Hume (the app's RACE_LOOK)
    local RACE_SIZE = { 1.0, 1.0, 1.07, 1.07, 0.78, 0.78, 0.97, 1.15 };
    local GEN = ART.gen;
    local GEN_SCALE = 31 / GEN.TALL;          -- a Hume stands 31 grid pixels tall

    -- for each of the 22 mate frames: { the sheet's frame, squash, steps back }
    local GEN_OF = {};
    do
        local function put(from, to, squash, back)
            for k, f in ipairs(from) do GEN_OF[f] = { to[math.min(k, #to)], squash or 1, back or 0 }; end
        end
        put(MATE_POSE.idle, GEN_POSE.idle);
        put(MATE_POSE.walk, GEN_POSE.walk);
        put(MATE_POSE.swing, GEN_POSE.attack);
        put(MATE_POSE.thrust, GEN_POSE.attack);
        put(MATE_POSE.shoot, GEN_POSE.attack);
        put(MATE_POSE.cast, GEN_POSE.ability);                  -- a mage's attack is its spell
        put(MATE_POSE.win, GEN_POSE.ability);
        put(MATE_POSE.hurt, GEN_POSE.hurt);
        put(MATE_POSE.evade, { GEN_POSE.idle[1] }, 1, 5);       -- the sheets have no dodge: a step back
        put(MATE_POSE.sit, { GEN_POSE.idle[2] }, 0.82);         -- nor a seat: hunkered down
    end

    local function hasSheet(job) return ART.jobs[job] == true; end

    -----------------------------------------------------------------------
    -- Vana'diel time, worked out the way the server does: 25 Vana'diel minutes to an Earth minute
    -----------------------------------------------------------------------
    local function vanaHour(unix)
        local mins = math.floor(((unix - 1009810800) / 60) * 25) + 886 * 518400;
        return math.floor((mins % 1440) / 60);
    end
    local function timeOfDay(hour)
        if hour >= 4 and hour < 6 then return 'dawn'; end
        if hour >= 6 and hour < 17 then return 'day'; end
        if hour >= 17 and hour < 20 then return 'dusk'; end
        return 'night';
    end
    S.vanaHour, S.timeOfDay = vanaHour, timeOfDay;

    -----------------------------------------------------------------------
    -- the venture's timeline
    -----------------------------------------------------------------------
    -- Where a venture stands at `sec` seconds in: the phase, the camp, the monster being fought and its HP.
    function S.stateAt(events, sec, over)
        local camp, arrive = '', 0;
        for _, e in ipairs(events) do
            if e.k == 'arrive' then camp, arrive = e.camp or '', e.t or 0; break; end
        end
        local last, nxt, rest;
        for _, e in ipairs(events) do
            if (e.k == 'arrive' or e.k == 'move') and e.t <= sec and e.camp then camp = e.camp; end
            if e.k == 'rest' and e.t <= sec and sec < e.t + (e.d or 0) then rest = e; end
            if e.k == 'kill' then
                if e.t <= sec then last = e; elseif not nxt then nxt = e; end
            end
        end
        local phase = over and 'home' or (sec < arrive and 'road' or (rest and 'rest' or 'fight'));
        local from = last and last.t or arrive;
        local to = nxt and nxt.t or (from + 120);
        local hp = nxt and math.max(0.03, 1 - (sec - from) / math.max(1, to - from)) or 1;
        return { phase = phase, camp = camp, fighting = nxt or last, last = last, hp = hp,
                 roadT = (arrive ~= 0) and math.min(1, sec / arrive) or 1 };
    end

    -- who stands in the scene: the mates first, then the party's other adventurers (six at most)
    function S.membersOf(mates, party)
        local out = {};
        for _, m in ipairs(mates or {}) do
            out[#out + 1] = { kind = 'mate', race = m.race or 1, job = JOBS[m.job or 1] or 'WAR', face = m.face or 0, weapon = m.weapon or 0 };
        end
        for i, p in ipairs(party or {}) do
            local h = 0;
            local name = tostring(p.name or '');
            for k = 1, #name do h = (h * 31 + name:byte(k)) % 4294967296; end
            out[#out + 1] = { kind = 'party', idx = (h + (i - 1)) % math.max(1, ART.party_count), job = p.job };
        end
        while #out > 6 do out[#out] = nil; end
        return out;
    end

    -- The mate frame for one of the old 10 poses. A job with a sheet is played more slowly: its frames are whole
    -- drawings, not in-betweens, and flicker when rushed.
    local CYCLE = { 0, 1, 2, 1 };
    local function mateFrame(old, job, step, gen)
        local P = MATE_POSE;
        local attack = CASTERS[job] and P.cast or (THRUST[job] and P.thrust or (SHOOT[job] and P.shoot or P.swing));
        if old == FRAME.idle0 or old == FRAME.idle1 then return P.idle[CYCLE[math.floor(step / (gen and 3 or 1)) % 4 + 1] + 1]; end
        if old == FRAME.walk0 or old == FRAME.walk1 then return P.walk[CYCLE[math.floor(step / (gen and 2 or 1)) % 4 + 1] + 1]; end
        if old == FRAME.atk0 then return attack[1]; end
        if old == FRAME.atk1 then return attack[#attack]; end
        if old == FRAME.cast then return P.cast[math.floor(step / (gen and 3 or 1)) % 2 + 1]; end
        if old == FRAME.hurt then return P.hurt[1]; end
        if old == FRAME.sit then return P.sit[1]; end
        if old == FRAME.win then return P.win[math.floor(step / (gen and 3 or 1)) % 2 + 1]; end
        return P.idle[1];
    end
    S.mateFrame = mateFrame;

    -----------------------------------------------------------------------
    -- pictures
    -----------------------------------------------------------------------
    local function file(kind, name) return ASSETS .. kind .. '\\' .. name .. '.png'; end

    -- Kaza's pixelled monster for this camp monster by name, else the drawn look
    local function mobArt(mob)
        local own = tostring(mob.name or ''):gsub('[^A-Za-z0-9]', '_');
        if ART.named[own] then
            return file('mt', own), ART.mobt, MOBT_SCALE;
        end
        local look = ART.mobs[mob.look or ''] and mob.look or 'slime';
        return file('m', look), ART.mob, MOB_SCALE;
    end

    -----------------------------------------------------------------------
    -- the scene
    -----------------------------------------------------------------------
    function S.draw(X, Y, P, o)
        local W, H = SCENE_W * P, SCENE_H * P;
        if gfx.dry then return W, H; end
        local camps = o.camps or {};
        local events = o.events or {};
        local sec = o.sec or 0;
        local tick = o.still and 0 or (o.tick or 0);
        local st = S.stateAt(events, sec, o.over);
        local phase = o.still or st.phase;
        local camp = camps[st.camp] or o.anyCamp;
        local sceneName = (camp and ART.scenes[camp.scene or '']) and camp.scene or 'ronfaure';
        local fe = (st.fighting and st.fighting.c) and camps[st.fighting.c] or camp;
        local mob;
        if fe and st.fighting and st.fighting.m ~= nil then mob = fe.mobs[st.fighting.m + 1]; elseif camp then mob = camp.mobs[1]; end
        local members = S.membersOf(o.mates, o.party);
        local c = tick % 18;
        -- a mate with a sheet of its own makes its other move on every fourth turn: a fighter its job's ability (nothing
        -- lands on the monster then), a mage a blow with its weapon in place of a spell
        local function other(m, i)
            return m.kind == 'mate' and hasSheet(m.job) and (math.floor((tick - i * 3) / 18) + i) % 4 == 3;
        end
        local function special(m, i) return other(m, i) and not CASTERS[m.job]; end
        local hitNow, hitAfter = false, false;
        if phase == 'fight' then
            for n, m in ipairs(members) do
                local i = n - 1;
                if c == (i * 3 + 1) % 18 and not special(m, i) then hitNow = true; end
                if c == (i * 3 + 2) % 18 and not special(m, i) then hitAfter = true; end     -- the frame after a hit
            end
        end
        local tod = (camp and INDOOR[camp.scene or '']) and 'day' or timeOfDay(vanaHour(o.unix or os.time()));
        local tint = TINT[tod];
        -- a kill a moment ago: the fallen monster fades out (and the next one fades in) with the exp it gave
        local since = st.last and (sec - st.last.t) or 99;
        local fallen;
        if phase == 'fight' and st.last and since >= 0 and since < 2.5 and st.last ~= st.fighting then
            local fc = st.last.c and camps[st.last.c] or camp;
            fallen = fc and fc.mobs[(st.last.m or 0) + 1] or nil;
        end
        local shake = hitNow and (((tick * 7) % 3) - 1) or 0;
        local dmg = 20 + ((tick * 37) % 140);
        local crit = dmg > 140;

        -- everything below is placed from the scene's corner, moved by the shake, and cut to the scene
        gfx.clip(X, Y, X + W, Y + H);
        gfx.rect(X, Y, X + W, Y + H, gfx.col('#101828'));
        local ox, oy = X + shake * P, Y + (hitNow and 1 or 0) * P;
        local function px(gx) return ox + gx * P; end
        local function py(gy) return oy + gy * P; end
        local function box(gx, gy, gw, gh, col, round) gfx.rect(px(gx), py(gy), px(gx + gw), py(gy + gh), gfx.col(col), round); end
        local function pill(gx, gy, gw, gh, col) box(gx, gy, gw, gh, col, gh * P / 2); end
        local SC = ART.scene;

        local function full(kind)
            local tex = gfx.tex(file(kind, sceneName));
            gfx.image(tex, ox, oy, ox + W, oy + H, 0, 0, SC.pw / SC.w, SC.ph / SC.h);
        end

        -- one frame of a sheet whose frames are `grid` pixels square, feet at x, y
        local function sheet(path, L, frame, x, y, scale, alpha)
            if alpha ~= nil and alpha <= 0 then return; end
            local w, h = L.grid * scale * P, L.grid * scale * P;
            local left = math.floor((x - (L.grid * scale) / 2) * P + 0.5);
            local top = math.floor((y - L.grid * scale) * P + 0.5);
            gfx.sprite(gfx.tex(path), L, frame, ox + left, oy + top, ox + left + w, oy + top + h,
                (alpha ~= nil and alpha < 1) and gfx.col('#FFFFFF', alpha) or nil);
        end

        -- a squad mate from its job's sheet: the file of its race look, sized by its race
        local function mate(m, frame, x, y)
            local race = math.max(1, math.min(8, math.floor(m.race or 1)));
            local job = hasSheet(m.job) and m.job or 'WAR';
            local g = GEN_OF[frame] or GEN_OF[0];
            local sx = GEN_SCALE * RACE_SIZE[race] * P;          -- screen pixels for one of the frame's pixels
            local sy = sx * g[2];
            local left = math.floor((x - g[3]) * P - GEN.CX * sx + 0.5);
            local top = math.floor(y * P - GEN.FOOT * sy + 0.5);
            gfx.sprite(gfx.tex(file('gm', job .. '_' .. race)), GEN, g[1], ox + left, oy + top, ox + left + GEN.FW * sx, oy + top + GEN.FH * sy);
        end

        full('bg');

        if phase == 'fight' and mob then
            pill(MOB_AT[1] - 16, MOB_AT[2] - 3, 32, 6, 'rgba(0,0,0,0.25)');
            if fallen then
                local path, L, scale = mobArt(fallen);
                sheet(path, L, 3, MOB_AT[1] + 4 + since * 3, MOB_AT[2], scale, math.max(0, 1 - since / 1.2));
            end
            do
                local path, L, scale = mobArt(mob);
                local frame = hitNow and 3 or ((c % 9 == 4) and 2 or ((tick % 4 < 2) and 0 or 1));
                sheet(path, L, frame, MOB_AT[1] + (hitNow and 2 or 0), MOB_AT[2], scale,
                    fallen and math.min(1, math.max(0, (since - 0.8) / 1.2)) or nil);
            end
            if hitNow then                                       -- sparks where the blow lands
                for k = 0, 5 do
                    local a = (k / 6) * math.pi * 2 + tick;
                    local sx, sy = MOB_AT[1] - 8 + math.cos(a) * 12, MOB_AT[2] - 24 + math.sin(a) * 9;
                    box(sx, sy, 3, 3, '#5A3000');
                    box(sx + 0.5, sy + 0.5, 2, 2, (k % 2 == 1) and '#FFE680' or '#FFFFFF');
                end
            end
            if hitNow or hitAfter then
                local a = hitAfter and 0.55 or 1;
                gfx.shadowed(px(MOB_AT[1] - 8), py(MOB_AT[2] - 44 - (hitAfter and 6 or 0)), gfx.col(crit and '#FFE060' or '#FFFFFF', a),
                    gfx.col('#000000', a), tostring(dmg), (crit and 11 or 9) * P, true);
            end
            if fallen then
                local a = math.max(0, 1 - since / 2.5);
                gfx.shadowed(px(MOB_AT[1] - 18), py(MOB_AT[2] - 50 - since * 8), gfx.col('#9EF0FF', a), gfx.col('#000000', a),
                    st.last.x and ('+' .. tostring(st.last.x) .. ' EXP') or 'Defeated!', 8 * P, true);
            end
        end

        -- the party, the ones further back first
        local order = {};
        for n, m in ipairs(members) do order[#order + 1] = { m = m, i = n - 1, spot = SPOTS[n] }; end
        table.sort(order, function(a, b) return a.spot[2] < b.spot[2]; end);
        for _, it in ipairs(order) do
            local m, i, spot = it.m, it.i, it.spot;
            local frame = (tick % 6 < 3) and FRAME.idle0 or FRAME.idle1;
            local mf = nil;                  -- a squad mate's own frame (22 of them), when it differs
            local x = spot[1];
            if phase == 'road' then
                frame = ((tick + i) % 4 < 2) and FRAME.walk0 or FRAME.walk1;
                x = spot[1] - 70 * (1 - st.roadT) + ((tick % 2 == 1) and 0.5 or 0);
            elseif phase == 'rest' then
                frame = FRAME.sit;
            elseif phase == 'home' then
                frame = (tick % 8 < 5) and FRAME.win or FRAME.idle0;
            else
                local k = (c - i * 3 + 18) % 18;
                local own = special(m, i);                           -- a fighter's ability this turn, not its attack
                local casts = CASTERS[m.job] and not other(m, i);    -- a mage's spell (on its other turn: its weapon)
                if k == 0 then frame = casts and FRAME.cast or FRAME.atk0;
                elseif k == 1 then frame = casts and FRAME.cast or FRAME.atk1; end
                if k == 1 and not own and not casts and not SHOOT[m.job] then x = x + 6; end
                if m.kind == 'mate' then
                    -- the whole move: wind-up, strike, follow-through (a cast or an ability: raise, then release)
                    local atk = (casts or own) and MATE_POSE.cast or (THRUST[m.job] and MATE_POSE.thrust
                        or (SHOOT[m.job] and MATE_POSE.shoot or MATE_POSE.swing));
                    if k <= 2 then mf = atk[math.min(#atk, k + 1)];
                    elseif i == 0 and c % 9 == 4 then mf = ((math.floor(c / 9) + i) % 2 == 1) and MATE_POSE.evade[1] or MATE_POSE.hurt[1]; end
                end
            end
            local casting = frame == FRAME.cast;
            pill(x - 9, spot[2] - 2, 18, 4, 'rgba(0,0,0,0.25)');
            if casting then                                          -- a glow at the caster's feet, motes rising
                pill(x - 12, spot[2] - 4, 24, 7, 'rgba(170,230,255,0.35)');
                for k = 0, 2 do
                    box(x - 6 + k * 6, spot[2] - 10 - ((tick * 3 + k * 5) % 22), 1.5, 1.5, (k == 1) and '#C8F4FF' or '#FFFFFF');
                end
            end
            if phase == 'road' then                                  -- dust behind the feet
                for k = 0, 1 do
                    box(x - 8 - k * 4 - ((tick + i) % 3), spot[2] - 2 - k, 2 + k, 2 + k, 'rgba(214,196,160,0.55)');
                end
            end
            if m.kind == 'mate' then
                mate(m, mf or mateFrame(frame, m.job, tick + i, hasSheet(m.job)), x, spot[2]);
            else
                sheet(file('p', 'k' .. tostring(m.idx + 1)), ART.party, frame, x, spot[2], 1);
            end
        end

        full('fg');

        if phase == 'rest' then                                      -- the campfire
            pill(CAMPFIRE[1] - 22, CAMPFIRE[2] - 10, 44, 16, 'rgba(255,150,60,0.22)');
            box(CAMPFIRE[1] - 6, CAMPFIRE[2] - 2, 12, 2, '#6A3A1C');
            local flames = { { -3, '#FF7020', 7 }, { 0, '#FFB030', 9 + (tick % 3) }, { 3, '#FF7020', 6 + ((tick + 1) % 2) }, { 0, '#FFF0A0', 4 + (tick % 2) } };
            for _, f in ipairs(flames) do
                box(CAMPFIRE[1] - 1.5 + f[1], CAMPFIRE[2] - 2 - f[3], 3, f[3], f[2]);
            end
            box(CAMPFIRE[1] - 1 + ((tick % 4) - 2), CAMPFIRE[2] - 16 - (tick % 8), 1, 1, '#FFD080');
        end
        if phase == 'home' then                                      -- the homecoming: sparkles over the party
            for k = 0, 7 do
                if (tick + k) % 3 ~= 0 then
                    box(20 + ((k * 53 + tick * 3) % 120), 30 + ((k * 29 + tick * 5) % 60), 2, 2, (k % 2 == 1) and '#FFE680' or '#FFFFFF');
                end
            end
        end
        if tint then gfx.vgrad(ox, oy, ox + W, oy + H, tint, nil, 32); end
        if phase == 'rest' then
            gfx.shadowed(px(72), py(70 - (tick % 6)), gfx.col('#FFFFFF'), gfx.col('#203060'), (tick % 12 < 6) and 'Z z' or 'z Z', 9 * P, true);
        end

        -- the name plates: the monster and its HP at the right, the camp at the left
        local function plate(text, right, maxShare, minShare, hp)
            local size = math.max(7 * P, o.minFont or 0);      -- (the app's letters, but never too small to read on a monitor)
            local pad = math.max(2 * P, size * 0.28);
            local maxw = W * maxShare - 2 * pad - 2;
            text = gfx.fit(text, size, maxw, true);
            local tw = gfx.width(text, size, true);
            local w = math.max(tw + 2 * pad + 2, W * (minShare or 0));
            local h = pad * 2 + 2 + math.floor(size * 1.15 + 0.5) + (hp and (4 * P) or 0);
            local x0 = right and (ox + W - 4 * P - w) or (ox + 4 * P);
            local y0 = oy + 4 * P;
            gfx.rect(x0, y0, x0 + w, y0 + h, gfx.col('rgba(10,16,48,0.82)'), 2 * P);
            gfx.frame(x0, y0, x0 + w, y0 + h, gfx.col('#A3ACD6'), 1);
            gfx.text(x0 + 1 + pad, y0 + 1 + pad, gfx.col('#F4E6B8'), text, size, true);
            if hp then
                local by = y0 + 1 + pad + math.floor(size * 1.15 + 0.5) + 1.5 * P;
                local bw = w - 2 - 2 * pad;
                gfx.rect(x0 + 1 + pad, by, x0 + 1 + pad + bw, by + 2.5 * P, gfx.col('#202838'), 1);
                gfx.rect(x0 + 1 + pad, by, x0 + 1 + pad + bw * math.floor(hp * 100 + 0.5) / 100, by + 2.5 * P,
                    gfx.col(hp < 0.25 and '#E05040' or (hp < 0.5 and '#E0B040' or '#58C050')), 1);
            end
        end
        if phase == 'fight' and mob then
            local lv = st.fighting and st.fighting.lv;
            plate(tostring(mob.name) .. (lv and ('  Lv.' .. tostring(lv)) or ''), true, 0.5, 0.34, st.hp);
        end
        if o.label and o.label ~= '' then plate(o.label, false, 0.58, 0, nil); end

        gfx.clip(nil);
        return W, H;
    end

    return S;
end

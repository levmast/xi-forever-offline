# Finding armor model numbers (MId) from the game client

Read-only tools used on 2026-11-19 for the golden casket costumes. Run on a machine that can see the
FFXI folder and the server; they never copy game files anywhere.

- `ft.py`: reads FTABLE/VTABLE (+ ROM2-9) and maps a model number to its game file:
  `F(race, slot, model)` for models 256-319, 320-575 and 576-607
  (bases 63067 / 70927 / 98211; race stride 448 / 1536 / 160; slot stride 64 / 256 / 32).
  Checked against 3,164 pieces whose numbers are in item_equipment.sql.
- `tn.py`: lists the texture names inside a model file.
- Needs the AltanaViewer name lists: `git clone https://github.com/CAProjects/AltanaViewer av` next to the scripts.
- Paths inside are for the Cowork VM (`~/mnt/...`); edit `G` and the server path for another machine.

A real model = a file that is not that race/slot's "None" placeholder (the most common file in the block).
To see a model in game: `!setplayermodel <model> <slot>` (4 head, 5 body, 6 hands, 7 legs, 8 feet).
- `tex.py`: decodes the textures in a model file (DXT data starts 85 bytes into each texture chunk) so a
  model can be identified by colour; `sheet(items, file)` draws a contact sheet. Keep the pictures on your PC
  (they are Square Enix art): `logs/` is git-ignored.
- Best identification trick: a recolour shares its texture *name* with the piece it was made from
  (e.g. model 487 uses Morrigan's Robe's texture name = Ruby Robe).

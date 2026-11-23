"""(delukard, 2026-11-22) "I have turned off the AH stocking and buying and it still has items on it": switching the
simulator off only stops new stock. SYSTEM > Settings > "Clear the auction house..." takes its listings off.
sqlite stands in for MariaDB.   python test_ah_clear.py
"""
import os
import sqlite3
import sys

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
import ah_sim as a
passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print('FAIL:', name)


db = sqlite3.connect(':memory:')
db.execute('CREATE TABLE auction_house (itemid INT, stack INT, seller INT, seller_name TEXT, date INT, price INT, buyer_name TEXT, sale INT, sell_date INT)')
rows = [(4096, 0, 0, 'Market', 1, 100, None, 0, 0),          # the simulator's, for sale
        (4096, 1, 0, 'Market', 1, 900, None, 0, 0),          # the simulator's stack, for sale
        (12495, 0, 0, 'Market', 1, 5000, None, 0, 0),        # the simulator's, for sale
        (4096, 0, 0, 'Market', 1, 100, 'Hurami', 100, 5),    # the simulator's, already sold: history
        (16705, 0, 21828, 'Hurami', 1, 3000, None, 0, 0),    # the player's own listing
        (16705, 0, 21900, 'Chuchumi', 1, 2500, None, 0, 0),  # a bot player's listing
        (4097, 0, 21828, 'Hurami', 1, 50, 'Market', 50, 7)]  # the player's sale to the simulator: history
db.executemany('INSERT INTO auction_house VALUES (?,?,?,?,?,?,?,?,?)', rows)
db.commit()

check('three listings go', a.clear_listings(db) == 3)
left = db.execute('SELECT seller, seller_name, sale FROM auction_house ORDER BY seller, sale').fetchall()
check('four rows are left', len(left) == 4)
check("the simulator has nothing for sale any more", db.execute('SELECT COUNT(*) FROM auction_house WHERE seller = 0 AND sale = 0').fetchone()[0] == 0)
check("the simulator's sales history stays", (0, 'Market', 100) in left)
check('your own listing stays', (21828, 'Hurami', 0) in left)
check("a bot player's listing stays", (21900, 'Chuchumi', 0) in left)
check('your sales history stays', (21828, 'Hurami', 50) in left)
check('a second press finds nothing', a.clear_listings(db) == 0)
check('the simulator counts no listings of its own afterwards', a.bot_counts(db) == ({}, {}))

gui = open(os.path.join(KIT, 'launcher_gui.pyw'), encoding='utf-8').read()
check('SYSTEM > Settings has the button', 'text="Clear the auction house..."' in gui and 'self.build_clear_ah()' in gui)
check('it asks first, and says so when the simulator is still on', 'messagebox.askyesno(title, text, parent=self)' in gui and 'The simulator is switched ON' in gui)
check('a database that cannot be reached is explained', 'The database could not be reached' in gui)
print(f'{passed} passed, {failed} failed')
sys.exit(1 if failed else 0)

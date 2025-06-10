#!/usr/bin/env python3
import sqlite3
import argparse
import arxiv
import sys
import re
from urllib.parse import urlparse
from datetime import datetime
import webbrowser
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Input, ListView, ListItem, Label
from textual.containers import Container


#Modern arxiv ids
ARXIV_REGEX_NEW = r'\d{4}\.\d{4,5}(v\d+)?'
# Old arxiv ids #TODO
ARXIV_REGEX_OLD = re.compile(r'arxiv.org/[^\/]+/([\w-]+\/[\w\.]+?)(\.pdf)?$', re.I)
ARXIV_REGEX = ARXIV_REGEX_NEW or ARXIV_REGEX_OLD
ARXIV_REGEX = r'([\w-]+\/[\w\.]+?)(\.pdf)?$' 
ARXIV_REGEX = r'\b([\w-]+\/[\w\.]+?)(\.pdf)?$'

DB_PATH = 'babel.db'
# instantiate a single Client to avoid deprecated Search.results()
client = arxiv.Client()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS papers (
        id INTEGER PRIMARY KEY,
        arxiv_id TEXT UNIQUE,
        title TEXT,
        summary TEXT,
        published TEXT,
        authors TEXT,
        url TEXT
    )''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE
    )''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS paper_tags (
        paper_id INTEGER,
        tag_id INTEGER,
        UNIQUE(paper_id, tag_id),
        FOREIGN KEY(paper_id) REFERENCES papers(id),
        FOREIGN KEY(tag_id) REFERENCES tags(id)
    )''')
    conn.commit()
    conn.close()

def get_conn():
    return sqlite3.connect(DB_PATH)

def extract_arxiv_id(s: str) -> str:
    # from URL like https://arxiv.org/abs/1234.5678v1 or PDF link
    m = re.search(r'arxiv\.org/(?:abs|pdf)/([^/]+)', s)
    if m:
        return m.group(1)
    return s.strip()

def choose_from_results(results):
    for i, entry in enumerate(results, 1):
        print(f"{i}. {entry.title} [{entry.get_short_id()}], authors: {', '.join(a.name for a in entry.authors)}")
    choice = input(f"Select paper [1–{len(results)}] or 0 to cancel: ")
    try:
        i = int(choice)
    except ValueError:
        return None
    if i < 1 or i > len(results):
        return None
    return results[i-1]

def add_paper(arg, in_tui=False, app=None):
    if in_tui and app:
        app.log_message("Adding paper: " + arg)
    aid = extract_arxiv_id(arg)
    # if it doesn’t look like an arXiv ID, do a title search
    if not re.match(r'\d{4}\.\d{4,5}(v\d+)?', aid):
        print("Searching arXiv for title…")
        if in_tui and app:
            app.log_message("Searching arXiv for title…")
        q = f'ti:{arg}'
        search = arxiv.Search(query=q, max_results=5)
        results = list(client.results(search))
        if not results:
            if in_tui and app:
                app.log_message("No matches found.")
            print("No matches found.")
            return
        if in_tui and app:
            # make a selectable list of results
            #TODO: make these look nicer
            items = [ListItem(Label(f"{entry.title} {entry.get_short_id()}, authors: {', '.join(a.name for a in entry.authors)}")) for _, entry in enumerate(results)]
            list_view = ListView(*items, id="search_results")
            app.mount(list_view)
            list_view.focus()

 
        else:
            entry = choose_from_results(results)
            if entry is None:
                print("Cancelled.")
                return
    else:
        search = arxiv.Search(id_list=[aid])
        entry = next(client.results(search), None)
        if entry is None:
            print(f"No arXiv paper found with id {aid}.")
            return

    # conn = get_conn()
    # c = conn.cursor()
    # try:
    #     c.execute('''
    #         INSERT INTO papers (arxiv_id, title, summary, published, authors, url)
    #         VALUES (?,?,?,?,?,?)
    #     ''', (
    #         entry.get_short_id(),
    #         entry.title,
    #         entry.summary,
    #         entry.published.strftime('%Y-%m-%d'),
    #         ', '.join(a.name for a in entry.authors),
    #         entry.entry_id
    #     ))
    #     pid = c.lastrowid
    #     conn.commit()
    #     print(f"Added paper “{entry.title}” ({entry.get_short_id()}).")
    # except sqlite3.IntegrityError:
    #     c.execute('SELECT id FROM papers WHERE arxiv_id=?', (entry.get_short_id(),))
    #     pid = c.fetchone()[0]
    #     print(f"Paper already in DB (id={pid}).")

    # tags = input("Enter tags (comma-separated), or leave blank: ").strip()
    # if tags:
    #     for tag in [t.strip() for t in tags.split(',') if t.strip()]:
    #         c.execute('INSERT OR IGNORE INTO tags (name) VALUES (?)', (tag,))
    #         c.execute('SELECT id FROM tags WHERE name=?', (tag,))
    #         tid = c.fetchone()[0]
    #         c.execute('INSERT OR IGNORE INTO paper_tags (paper_id, tag_id) VALUES (?,?)', (pid, tid))
    #     conn.commit()
    #     print("Tags updated.")
    # conn.close()

def search_title(keywords):
    conn = get_conn(); c = conn.cursor()
    terms = keywords.split()
    query = "SELECT id, title, authors, published FROM papers WHERE " + " AND ".join("title LIKE ?" for _ in terms)
    args = [f'%{t}%' for t in terms]
    c.execute(query, args)
    rows = c.fetchall()
    if not rows:
        print("No papers found.")
        return []
    else:
        pids = []
        for pid, title, authors, pub in rows:
            pids.append(pid)
            print(f"[{pid}] {title} — {authors} ({pub})")
    conn.close()
    return pids

def search_author(name):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT id, title, authors, published FROM papers WHERE authors LIKE ?", (f'%{name}%',))
    rows = c.fetchall()
    if not rows:
        print("No papers found.")
    else:
        for pid, title, authors, pub in rows:
            print(f"[{pid}] {title} — {authors} ({pub})")
    conn.close()

def search_tag(tag):
    conn = get_conn(); c = conn.cursor()
    c.execute('''
      SELECT p.id, p.title, p.authors, p.published
      FROM papers p
      JOIN paper_tags pt ON p.id=pt.paper_id
      JOIN tags t ON pt.tag_id=t.id
      WHERE t.name LIKE ?
    ''', (f'%{tag}%',))
    rows = c.fetchall()
    if not rows:
        print("No papers found.")
    else:
        for pid, title, authors, pub in rows:
            print(f"[{pid}] {title} — {authors} ({pub})")
    conn.close()

# def add_tags(paper_id, tags):
#     conn = get_conn(); c = conn.cursor()
#     c.execute('SELECT id FROM papers WHERE id=?', (paper_id,))
#     if not c.fetchone():
#         print("No such paper ID.")
#         conn.close()
#         return
#     for tag in [t.strip() for t in tags.split(',') if t.strip()]:
#         c.execute('INSERT OR IGNORE INTO tags (name) VALUES (?)', (tag,))
#         c.execute('SELECT id FROM tags WHERE name=?', (tag,))
#         tid = c.fetchone()[0]
#         c.execute('INSERT OR IGNORE INTO paper_tags (paper_id, tag_id) VALUES (?,?)', (paper_id, tid))
#     conn.commit()
#     conn.close()
#     print("Tags added.")



def list_papers():
    """List all papers in the database."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT p.id, p.arxiv_id, p.title, p.authors, p.published
        FROM papers p
        ORDER BY p.id ASC
    """)
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("No papers in database.")
        return
    # get the pids as a list
    pids = []
    for pid, aid, title, authors, pub in rows:
        pids.append(pid)
        print(f"[{pid}] {title} ({aid}) — {authors} · {pub}")
    return pids 

def list_tags():
    """
    Fetch and print all tags in the database.
    """
    conn = get_conn()
    c = conn.cursor()
    # Optionally include a count of how many papers have each tag:
    c.execute("""
        SELECT t.id, t.name, COUNT(pt.paper_id) AS cnt
        FROM tags t
        LEFT JOIN paper_tags pt ON t.id = pt.tag_id
        GROUP BY t.id, t.name
        ORDER BY t.name
    """)
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("No tags in database.")
        return

    for tid, name, cnt in rows:
        print(f"[{tid}] {name} — {cnt} paper{'s' if cnt != 1 else ''}")

def remove_paper(arg):
    """
    Remove a paper from the database by title keywords.
    Prompts user to select among multiple matches and confirms before deleting.
    """
    conn = get_conn()
    c = conn.cursor()

    # 1) find matching papers by title
    terms = arg.split()
    query = "SELECT id, title, authors, published FROM papers WHERE " + \
            " AND ".join("title LIKE ?" for _ in terms)
    params = [f"%{t}%" for t in terms]
    c.execute(query, params)
    results = c.fetchall()

    if not results:
        print("No matching titles found.")
        conn.close()
        return

    # 2) pick one if multiple
    if len(results) == 1:
        pid, title, authors, pub = results[0]
    else:
        print("Multiple papers found. Please choose:")
        for idx, (pid, title, authors, pub) in enumerate(results, 1):
            print(f" {idx}. [{pid}] {title} — {authors} ({pub})")
        choice = input(f"Select 1–{len(results)} or 0 to cancel: ")
        try:
            i = int(choice)
        except ValueError:
            print("Cancelled.")
            conn.close()
            return
        if i < 1 or i > len(results):
            print("Cancelled.")
            conn.close()
            return
        pid, title, authors, pub = results[i-1]

    # 3) confirm deletion
    confirm = input(f"Are you sure you want to delete “{title}” (ID {pid})? [y/N]: ").strip().lower()
    if confirm not in ('y', 'yes'):
        print("Aborted.")
        conn.close()
        return

    # 4) delete tags link and paper
    c.execute("DELETE FROM paper_tags WHERE paper_id=?", (pid,))
    c.execute("DELETE FROM papers        WHERE id=?",        (pid,))
    conn.commit()
    conn.close()
    print(f"Deleted paper ID {pid}: “{title}”.")


def get_paper_by_id(paper_id):
    """
    Fetch a paper by its ID from the database.
    Returns a tuple (arxiv_id, title, authors, published, url) or None if not found.
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT arxiv_id, title, authors, published, url FROM papers WHERE id=?", (paper_id,))
    row = c.fetchone()
    conn.close()
    return row if row else None

def get_paper_by_arxiv_id(arxiv_id):
    """
    Fetch a paper by its arXiv ID from the database.
    Returns a tuple (id, title, authors, published, url) or None if not found.
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, title, authors, published, url FROM papers WHERE arxiv_id=?", (arxiv_id,))
    row = c.fetchone()
    conn.close()
    return row if row else None

def cli():
    init_db()
    p = argparse.ArgumentParser(prog='babel', description='Babel: a tiny arXiv paper DB')
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('-a', metavar='"ID|URL|title"', help='Add paper by arXiv ID, URL, or title')
    group.add_argument('-s', metavar='"keywords"', help='Search papers by title keywords')
    group.add_argument('-sa', metavar='"author"', help='Search papers by author name')
    group.add_argument('-st', metavar='"tag"', help='Search papers by tag')
    group.add_argument('-at', nargs=2, metavar=('PAPER_ID','"tag1,tag2"'),
                       help='Add tag(s) to existing paper')
    group.add_argument('-ls', action='store_true', help='List all papers')
    group.add_argument('-lt', action='store_true', help='List all tags')
    group.add_argument('-rm', metavar='"title-keywords"', help='Remove paper by title')

    args = p.parse_args()

    if args.a:
        add_paper(args.a)
    elif args.s:
        search_title(args.s)
    elif args.sa:
        search_author(args.sa)
    elif args.st:
        search_tag(args.st)
    elif args.at:
        pid, tags = args.at
        # add_tags(pid, tags)
    elif args.ls:
        list_papers()
    elif args.lt:
        list_tags()
    elif args.rm:
        remove_paper(args.rm)

class Paper(ListItem):
    def __init__(self, label: str, arxiv_id: str) -> None:
        super().__init__()
        self.label = label
        self.arxiv_id = arxiv_id

    def compose( self ) -> ComposeResult:
        yield Label(self.label)
        yield Label(self.arxiv_id)

class PaperTagging(Input):
    def __init__(self, arxiv_id: str, id: str) -> None:
        super().__init__(id=id, placeholder="Enter tags for the paper (comma-separated)")
        self.arxiv_id = arxiv_id



class BabelApp(App):
    #TODO: get the height of the console to be 1 line, make the table take up all of the rest of the space
    CSS = """
        #overlay {
        background: rgba(0,0,0,0.5);
        }
        #search_input, #tag_table {
        width: 60%;
        align: center bottom;
        max-height: 50%;
        }

        ListView {
            height: auto;
            margin: 2 2;
        }

        Label {
            padding: 1 2;
        }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("h", "cursor_left", "←"),
        ("j", "cursor_down", "↓"),
        ("k", "cursor_up", "↑"),
        ("l", "cursor_right", "→"),
        ("/", "show_search", "Search"),
        ("t", "show_tags", "Tag Filter"),
        ("r", "reset", "Reset"),
        ("a", "add_paper", "Add Paper"),
        ("x", "remove_paper", "Remove Paper"),
        ("e", "edit_tags", "Edit Tags"),
        ("o", "open_paper", "Open Paper"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield DataTable(id="papers")
        yield Footer()

    def on_mount(self) -> None:
        # initialize the database if it doesn't exist
        init_db()
        self.theme = "gruvbox"
        self.title = "babel"
        self.filter_query = None
        self.filter_tag = None
        # load the papers table
        self.load_table()


    def load_table(self) -> None:
        table = self.query_one("#papers", DataTable)
        table.clear(columns=True)
        table.add_columns("ArXiv ID", "Title", "Authors", "Tags")
        table.cursor_type = "row"

        sql = """
          SELECT p.arxiv_id, p.title, p.authors,
                 COALESCE(GROUP_CONCAT(t.name, ', '), '') AS tags
          FROM papers p
          LEFT JOIN paper_tags pt ON p.id = pt.paper_id
          LEFT JOIN tags t ON pt.tag_id = t.id
        """
        where, params = [], []
        if self.filter_tag:
            where.append("t.name = ?"); params.append(self.filter_tag)
        if self.filter_query:
            where.append("(p.title LIKE ? OR p.authors LIKE ?)")
            q = f"%{self.filter_query}%"
            params.extend([q, q])
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY p.id ORDER BY p.published DESC"

        conn = sqlite3.connect(DB_PATH)
        for aid, title, authors, tags in conn.execute(sql, params):
            names = [n.strip() for n in authors.split(", ")] if authors else []
            last5 = [n.split()[-1] for n in names[:5]]
            disp_auth = ", ".join(last5)
            table.add_row(aid, title, disp_auth, tags)
        conn.close()

    # writes a notification message as a toast widget
    def log_message(self, message: str, sev='information') -> None:
        self.notify(message, severity=sev) #type: ignore
        
    # vim-style movement actions
    def action_cursor_down(self):
        self.query_one("#papers", DataTable).action_cursor_down()

    def action_cursor_right(self):
        self.query_one("#papers", DataTable).action_cursor_right()

    def action_cursor_up(self):
        self.query_one("#papers", DataTable).action_cursor_up()

    def action_cursor_left(self):
        self.query_one("#papers", DataTable).action_cursor_left()

    def action_open_paper(self):
        # open the selected paper in a browser
        table = self.query_one("#papers", DataTable)
        arxiv_id = table.get_cell_at(table.cursor_coordinate)
        url = f"https://arxiv.org/abs/{arxiv_id}"
        webbrowser.open(url)

    def action_add_paper(self):
        # prompt for arXiv ID, title, or url
        aid = Input(placeholder="Enter arXiv ID, title, or url to add")
        self.mount(aid)
        aid.focus()
    
    def extract_arxiv_id(self, s: str) -> str:
        # from URL like https://arxiv.org/abs/1234.5678v1 or PDF link
        m = re.search(ARXIV_REGEX, s)
        if m:
            return m.group(1)
        return s.strip()

    def get_paper_id_from_arxiv_id(self, aid: str) -> int:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id FROM papers WHERE arxiv_id=?', (aid,))
        row = c.fetchone()
        conn.close()
        if row:
            return row[0]
        else:
            return -1

    # adds tags to the paper with the given arXiv ID
    def add_tags(self, aid:str, tags: str) -> None:
        pid = self.get_paper_id_from_arxiv_id(aid)
        if pid == -1:
            self.log_message("No such paper ID.", 'error')
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for tag in [t.strip() for t in tags.split(',') if t.strip()]:
            c.execute('INSERT OR IGNORE INTO tags (name) VALUES (?)', (tag,))
            c.execute('SELECT id FROM tags WHERE name=?', (tag,))
            tid = c.fetchone()[0]
            c.execute('INSERT OR IGNORE INTO paper_tags (paper_id, tag_id) VALUES (?,?)', (pid, tid))
        conn.commit()
        conn.close()
        self.load_table()

    def set_tags(self, aid: str, tags: str) -> None:
        # replaces all existing tags with the new ones
        pid = self.get_paper_id_from_arxiv_id(aid)
        if pid == -1:
            self.log_message("No such paper ID.", 'error')
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # first delete all existing tags for this paper
        c.execute('DELETE FROM paper_tags WHERE paper_id=?', (pid,))
        # then add the new tags
        conn.commit()
        conn.close()
        self.add_tags(aid, tags)


    # adds a paper based on user input
    def add_paper(self, user_inp):
        # check if the input is a URL or arXiv ID
        aid = self.extract_arxiv_id(user_inp)
        
        # if the extracted content does not look like an arXiv ID, do a title search
        if not re.match(ARXIV_REGEX, user_inp):
            search = arxiv.Search(query=f'ti:{aid}', max_results=5)
            results = list(client.results(search))
            if not results:
                # check the aid list
                search = arxiv.Search(id_list=[aid])
                results = list(client.results(search))
                if not results:
                    self.log_message(f"No arXiv paper found with id {aid}.", 'error')
                    return 2
                if len(results) == 1:
                    self.add_paper_internal(results[0].get_short_id())
                    return 0
            # make a selectable list of results
            items = [Paper(f"{entry.title}, authors: {', '.join(a.name for a in entry.authors)}", arxiv_id=entry.get_short_id()) for _, entry in enumerate(results)]
            lv = ListView(*items, id="search_results")
            self.mount(lv)
            lv.focus()
        else:
            self.add_paper_internal(aid)
        

    # adds a paper given the exact arXiv ID, no user interaction
    # this interfaces with the database directly
    def add_paper_internal(self, aid):
        self.log_message(f"Adding paper with arXiv ID: {aid}", 'information')
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # first check the database if the paper is already there
        c.execute('SELECT id FROM papers WHERE arxiv_id=?', (aid,))
        if c.fetchone():
            self.log_message(f"Paper with arXiv ID {aid} already exists in the database.", 'warning')
            conn.close()
            return 3 # exit code for already exists
        # search for the paper by ID on arxiv
        search = arxiv.Search(id_list=[aid])
        entry = next(client.results(search), None)
        if entry is None:
            self.log_message(f"No arXiv paper found with id {aid}.", 'error')
            return 2 # exit code for not found
        try:
            c.execute('''
                INSERT INTO papers (arxiv_id, title, summary, published, authors, url)
                VALUES (?,?,?,?,?,?)
            ''', (
                entry.get_short_id(),
                entry.title,
                entry.summary,
                entry.published.strftime('%Y-%m-%d'),
                ', '.join(a.name for a in entry.authors),
                entry.entry_id
            ))
            pid = c.lastrowid
            conn.commit()
            self.log_message(f"Added paper “{entry.title}” ({entry.get_short_id()}).", 'information')
        except sqlite3.IntegrityError:
            #TODO: I think this is redundant now
            c.execute('SELECT id FROM papers WHERE arxiv_id=?', (entry.get_short_id(),))
            pid = c.fetchone()[0]
            self.log_message(f"Paper already in DB (id={pid}).", 'warning')
            return 3 # exit code for already exists
        conn.commit()
        conn.close()
        self.load_table()
        # add tags to the paper
        paper_tagger = PaperTagging(arxiv_id=aid, id="tag_input") 
        self.mount(paper_tagger)
        paper_tagger.focus()
        
        return 0 # exit code for success


    def get_current_tags(self, arxiv_id:str) -> str:
        """
        Get the current tags for a paper with the given arXiv ID.
        Returns a comma-separated string of tags.
        """
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT GROUP_CONCAT(t.name, ', ')
            FROM tags t
            JOIN paper_tags pt ON t.id = pt.tag_id
            JOIN papers p ON pt.paper_id = p.id
            WHERE p.arxiv_id = ?
        ''', (arxiv_id,))
        tags = c.fetchone()[0]
        conn.close()
        return tags if tags else ""

    # editing the tags for a paper
    def action_edit_tags(self):
        # get the currently selected paper
        table = self.query_one("#papers", DataTable)
        if not table.cursor_coordinate:
            self.log_message("No paper selected.", 'error')
            return -1
        arxiv_id = table.get_cell_at(table.cursor_coordinate)
        # self.log_message(f"Editing tags for paper with arXiv ID: {arxiv_id}")
        # now make a input field, prepopulated with the current tags
        current_tags = self.get_current_tags(arxiv_id)
        tag_input = PaperTagging(arxiv_id=arxiv_id, id="tag_modification")
        tag_input.value = current_tags
        self.mount(tag_input)
        tag_input.focus()
        return 0

    # removing a paper, no confirmation
    def remove_paper(self, aid: str) -> None:
        # first remove all tags for this paper
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM paper_tags WHERE paper_id=(SELECT id FROM papers WHERE arxiv_id=?)', (aid,))
        # then remove the paper itself
        c.execute('DELETE FROM papers WHERE arxiv_id=?', (aid,))
        conn.commit()
        conn.close()
        self.log_message(f"Removed paper with arXiv ID: {aid}", 'information')
        self.load_table()
        return

    def action_remove_paper(self):
        # get the currently selected paper
        table = self.query_one("#papers", DataTable)
        if not table.cursor_coordinate:
            self.log_message("No paper selected.", 'error')
            return -1
        arxiv_id = table.get_cell_at(table.cursor_coordinate)
        # confirm removal
        confirm = PaperTagging(id="confirm_remove", arxiv_id=arxiv_id)
        confirm.placeholder = f"Are you sure you want to remove this paper? (y/N)"
        self.mount(confirm)
        confirm.focus()
        return 

    async def on_list_view_selected(self, event: ListView.Selected) -> None: 
        event.list_view.remove()
        aid = event.item.arxiv_id #type: ignore
        self.log_message(f"Selected paper: {aid}", 'information')
        self.add_paper_internal(aid)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        event.input.remove()
        if event.input.id == "tag_input":
            aid = event.input.arxiv_id #type: ignore
            # add tags to the last added paper
            tags = event.input.value.strip()
            if not tags:
                self.log_message("No tags entered.", 'warning')
                return
            else:
                self.log_message(f"Adding tags to paper {aid}: {tags}", 'information')
                self.add_tags(aid, tags)
        elif event.input.id == "tag_modification":
            aid = event.input.arxiv_id #type: ignore
            tags = event.input.value.strip()
            if not tags:
                self.log_message("No tags entered.", 'warning')
                return
            else:
                self.log_message(f"Modifying tags for paper {aid}: {tags}", 'information')
                self.set_tags(aid, tags)
        elif event.input.id == "confirm_remove":
            # remove the paper
            aid = event.input.arxiv_id #type: ignore
            if event.input.value.strip().lower() in ('y', 'yes'):
                self.log_message(f"Removing paper {aid}.")
                self.remove_paper(aid)
            else:
                self.log_message("Removal cancelled.")
        else:
            link = event.input.value.strip()
            self.add_paper(link)
            self.load_table()

def tui():
    BabelApp().run()    


if __name__ == '__main__':
    # cli()
    tui()




#TODO:
# tag filtering
# searching by title
# searching by author
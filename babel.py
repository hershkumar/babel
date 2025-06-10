#!/usr/bin/env python3
import sqlite3
import argparse
import arxiv
import sys
import re
from itertools import permutations
from typing import List
from urllib.parse import urlparse
from datetime import datetime
import webbrowser
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Input, ListView, ListItem, Label
from textual.suggester import SuggestFromList
from textual.containers import Container

ARXIV_REGEX = r'\b([\w-]+\/[\w\.]+?)(\.pdf)?$'

def strip_url(arg):
    arg = arg.strip()
    arg = arg.removeprefix("http://arxiv.org/abs/")
    arg = arg.removeprefix("https://arxiv.org/abs/")
    arg = arg.removeprefix("https://arxiv.org/pdf/")
    arg = arg.removeprefix("http://arxiv.org/pdf/")
    return arg.strip()


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


def all_comma_separated(arr: List[str]) -> List[str]:
    """
    Generate all comma-separated strings from the input list,
    of lengths 1 through len(arr), with no repeated elements.

    :param arr: List of unique strings.
    :return: List of comma-separated strings.
    """
    results: List[str] = []
    for r in range(1, len(arr) + 1):
        for perm in permutations(arr, r):
            results.append(", ".join(perm))
    return results


def get_all_tags() -> list[str]:
        # get all tags from the database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id, name FROM tags ORDER BY name')
        tags = c.fetchall()
        conn.close()
        return [f"{name}" for _, name in tags]

def get_all_tags_perm() -> list[str]:
        # get all tags from the database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id, name FROM tags ORDER BY name')
        tags = c.fetchall()
        conn.close()
        tags = [name for _, name in tags]
        tags = all_comma_separated(tags)
        return tags




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
        super().__init__(id=id, placeholder="Enter tags for the paper (comma-separated)", suggester=SuggestFromList(get_all_tags_perm(), case_sensitive=False))
        self.arxiv_id = arxiv_id 


class BabelApp(App):
    #TODO: get the height of the console to be 1 line, make the table take up all of the rest of the space
    CSS = """
        #overlay {
        background: rgba(0,0,0,0.5);
        }
        #search_input, #tag_table {
        width: 100%;
        align: center bottom;
        max-height: 50%;
        }
        #tag_filter, #tag_modification, #confirm_remove {
        width: 100%;
        }
        #papers {
            width: 100%;
            max-height: 95%;
            overflow-y: auto;    
        }
        ListView {
            height: auto;
            max-height: 60%;
            margin: 1 1;
        }

        Label {
            padding: 1 1;
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
        ('r', "reset", "Reset"),
        ('escape', 'reset', 'Reset'),
        ("a", "add_paper", "Add Paper"),
        ("x", "remove_paper", "Remove Paper"),
        ("e", "edit_tags", "Edit Tags"),
        ("o", "open_paper", "Open Paper"),
        ("space", "open_pdf", "Open PDF"),
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

    def get_tag_from_id(self, tag_id: int) -> str:
        # get the tag name from the database by ID
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT name FROM tags WHERE id=?', (tag_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return row[0]
        return ""

    

    # prompting for a set of tags to filter the papers by
    def action_show_tags(self):
        # prompt for a tag to filter the papers by
        tag_input = Input(placeholder="Enter tag to filter by (leave empty to reset)", id="tag_filter", suggester=SuggestFromList(get_all_tags_perm(), case_sensitive=False))
        self.mount(tag_input)
        tag_input.focus()

    # reset the table to show all papers
    def action_reset(self):
        self.filter_query = None
        self.filter_tag = None
        # self.log_message("Resetting filters.", 'information')
        self.load_table()

    def action_show_search(self):
        # prompt for a search query
        search_input = Input(placeholder="Enter search query (title, author, etc.)", id="search_input")
        self.mount(search_input)
        search_input.focus()


    def load_table(self) -> None:
        table = self.query_one("#papers", DataTable)
        table.clear(columns=True)
        table.zebra_stripes = True
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
        # truncate the title to a total of 50 characters, including the ellipsis
        truncation = 60
        trunc = lambda title: (title[:truncation-3] + '...') if len(title) > truncation else title
        for aid, title, authors, tags in conn.execute(sql, params):
            names = [n.strip() for n in authors.split(", ")] if authors else []
            last5 = [n.split()[-1] for n in names[:5]]
            disp_auth = ", ".join(last5)
            table.add_row(aid, trunc(title), disp_auth, tags)
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
        return

    def action_open_pdf(self):
        table = self.query_one("#papers", DataTable)
        arxiv_id = table.get_cell_at(table.cursor_coordinate)
        url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        webbrowser.open(url)
        return

    def action_add_paper(self):
        # prompt for arXiv ID, title, or url
        aid = Input(placeholder="Enter arXiv ID, title, author, or url to add")
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
        # aid = self.extract_arxiv_id(user_inp)
        aid = strip_url(user_inp)
        # if the extracted content does not look like an arXiv ID, do a title search
        if not re.match(ARXIV_REGEX, user_inp):
            search = arxiv.Search(query=f'ti:{aid}', max_results=20)
            results = list(client.results(search))
            if not results:
                # check the aid list, in case it matches something
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
            # self.log_message(f"Added paper “{entry.title}” ({entry.get_short_id()}).", 'information')
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

    def purge_unused_tags(self):
        """
        Remove tags that are not associated with any papers.
        This is useful for cleaning up the database.
        """
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            DELETE FROM tags
            WHERE id NOT IN (SELECT DISTINCT tag_id FROM paper_tags)
        ''')
        conn.commit()
        conn.close()
        return 

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
        # self.log_message(f"Removed paper with arXiv ID: {aid}", 'information')
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
        #TODO: This should not be a PaperTagging, maybe a yes/no button instead
        confirm = PaperTagging(id="confirm_remove", arxiv_id=arxiv_id)
        confirm.placeholder = f"Are you sure you want to remove this paper? (y/N)"
        self.mount(confirm)
        confirm.focus()
        return 

    async def on_list_view_selected(self, event: ListView.Selected) -> None: 
        event.list_view.remove()
        aid = event.item.arxiv_id #type: ignore
        # self.log_message(f"Selected paper: {aid}", 'information')
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
                # self.log_message(f"Adding tags to paper {aid}: {tags}", 'information')
                self.add_tags(aid, tags)
        elif event.input.id == "tag_modification":
            aid = event.input.arxiv_id #type: ignore
            tags = event.input.value.strip()
            if not tags:
                self.log_message("No tags entered.", 'warning')
                return
            else:
                # self.log_message(f"Modifying tags for paper {aid}: {tags}", 'information')
                self.set_tags(aid, tags)
        elif event.input.id == "confirm_remove":
            # remove the paper
            aid = event.input.arxiv_id #type: ignore
            if event.input.value.strip().lower() in ('y', 'yes'):
                # self.log_message(f"Removing paper {aid}.")
                self.remove_paper(aid)
            else:
                self.log_message("Removal cancelled.")
        elif event.input.id == "tag_filter":
            # get the tags to filter by 
            tag = event.input.value.strip()
            if not tag:
                self.log_message("Resetting tag filter.", 'information')
                self.filter_tag = None
            else:
                # self.log_message(f"Filtering by tag: {tag}", 'information')
                self.filter_tag = tag
            self.load_table()
        elif event.input.id == "search_input":
            # get the search query
            query = event.input.value.strip()
            if not query:
                self.log_message("Resetting search query.", 'information')
                self.filter_query = None
            else:
                # self.log_message(f"Searching for: {query}", 'information')
                self.filter_query = query
            self.load_table()
        else:
            link = event.input.value.strip()
            self.add_paper(link)
            self.load_table()
        # remove any unused tags from the database
        self.purge_unused_tags()

def tui():
    BabelApp().run()    

if __name__ == '__main__':
    tui()
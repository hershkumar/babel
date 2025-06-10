> ...the librarian deduced that the Library is "total"-perfect, complete, and whole-and that its bookshelves contain all possible combinations of the twenty-two orthographic symbols (a number which, though unimaginably vast, is not infinite)-that is, all that is able to be expressed, in every language.

~ Jorge Luis Borges, "The Library of Babel"

## Babel
Personal paper storage and management system. Supports tagging, searching, and viewing of papers from arxiv.org.

### TODO:
- [x] Implement tag filtering for display
- [x] Implement search functionality
- [x] When the last paper with a tag is deleted, remove the tag from database entirely
- [x] Instead of a tag selector ui, have a suggestor that autocompletes based on existing tags
- [ ] Implement cancelling adding papers or tagging
- [ ] Figure out the CSS formatting for all the elements
- [x] Space opens up the pdf directly, o opens the arxiv page
- [ ] Stress test more arxiv links
- [ ] Stress test the search and tagging functionality
- [ ] For APS papers, get the doi from the aps link, then use that to get the arxiv id. arxiv has a doi search?
- [ ] Try to speed up the arxiv api calls (?)
- [x] Figure out smooth scrolling for the selection when picking a paper
- [ ] Download the papers to a local folder for offline access? I assume python can open local pdfs.
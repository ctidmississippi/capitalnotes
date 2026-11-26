# Capitol Notes
A daily-built, Drudge-style political headline page. `build.py` pulls the feeds in `feeds.json`
(Google News search RSS + outlet RSS), clusters duplicate stories, ranks by number of outlets, and
writes `index.html`. A GitHub Action runs it every morning. Tooltips list the outlets that ran each story.

Setup: push to a new repo, then Settings > Pages > Deploy from branch `main` / root.
Edit `feeds.json` to change topics or sources; edit `template.html` for the look.
Run locally: `python3 build.py`


# Minimalist Bookmark Manager

A lightweight, single-file Python web application that manages your bookmarks using a simple, human-readable Markdown file as storage. It serves a raw HTML interface that is fast, simple, and works perfectly without JavaScript.

The main objective is to have a portable way of managing bookmarks, so that browser-hopping is easier. For example, using [Dillo](https://dillo-browser.github.io/) in tandem with [Firefox](https://www.firefox.com).

> Important note: this whole app was vibe coded with Gemini 3 Pro. Thus, don't expect perfect code quality or further substantial improvements. It does what it does well, and I only believe in vibe coding when the scope is clear and limited. From now on, any refactors and bug fixes will be done mostly manually.

## Getting Started

This project's environment is managed with **[uv](https://github.com/astral-sh/uv)** for fast and reliable dependency management.

### Prerequisites

* Python 3.x
* `uv` installed (see [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/))

### Installation & Running

```bash
git clone https://github.com/irisdominguez/pymarkmarks
uv sync
uv run pymarkmarks.py my_bookmarks.md
```
The navigate to the main interface [`http://127.0.0.1:5000`](http://127.0.0.1:5000)

## Features

* **Markdown Backed:** All data is stored in a clean `bookmarks.md` file using standard Markdown syntax (`- [Title](URL)`). The file is kept updated in real time, and any changes to the file are identified as soon as they happen (although they are not visible before the next page refresh).
* **Zero-JS Core:** The interface is built with raw HTML and CSS. JavaScript is used only as a progressive enhancement to preserve scroll position; the app functions without it.
* **Nested Folders:** Create deep folder structures to organize your links.
* **Favicon Management:**
    * Automatically downloads and caches favicons locally, in the background.
    * **Cleanup Tool:** A built-in button to delete cached icons for bookmarks you have removed.
* **Auto-Titling:** When adding a link, the app automatically fetches the page title and favicon for you.

## File Structure

* `pymarkmarks.py`: The single-file application logic.
* `bookmarks.md`: Your data (human-readable and portable).
* `favicons/`: A directory created automatically next to your markdown file to store cached icons.

Favicon folder is created at the same path as `bookmarks.md`, you can chose another location. 



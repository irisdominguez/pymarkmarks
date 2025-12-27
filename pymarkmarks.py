import os
import sys
import argparse
import hashlib
import threading
import requests
import re
from flask import Flask, render_template_string, request, redirect, url_for, send_from_directory
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# --- Configuration & Globals ---
app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for flash messages
BOOKMARKS_FILE = ""
FAVICONS_DIR = ""
LOCK = threading.Lock()

# --- Minimal CSS & JS ---
# We inject a small JS script for scroll preservation.
# It only runs if JS is enabled; otherwise the page works as standard HTML.
HEAD_CONTENT = """
<style>
    body { font-family: monospace; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
    ul { list-style-type: none; padding-left: 25px; border-left: 1px solid #eee; }
    li { margin: 5px 0; }
    .node-row { display: flex; align-items: center; gap: 8px; }
    .actions { font-size: 0.8em; color: #666; }
    .actions a { color: #888; text-decoration: none; margin: 0 2px;}
    .actions a:hover { color: #000; text-decoration: underline; }
    .main-link { text-decoration: none; color: #007bff; font-size: 1.1em;}
    .main-link:hover { text-decoration: underline; }
    .folder { font-weight: bold; color: #333; font-size: 1.1em; }
    .favicon { width: 16px; height: 16px; object-fit: contain; margin-right: 5px;}
    .placeholder-icon { width: 16px; height: 16px; display:inline-block; margin-right: 5px; }
    input[type="text"] { width: 100%; padding: 5px; margin-bottom: 10px; }
    button { padding: 5px 10px; cursor: pointer; }
    .nav-header { margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #eee; }
    .move-btn { font-weight: bold; text-decoration: none; font-size: 1.2em; cursor: pointer; }
    .flash { background: #eef; padding: 10px; margin-bottom: 10px; border: 1px solid #ccd; }
</style>
<script>
    // Progressive Enhancement: Preserve scroll position on reload
    document.addEventListener("DOMContentLoaded", function(event) { 
        var scrollpos = sessionStorage.getItem('scrollpos');
        if (scrollpos) window.scrollTo(0, scrollpos);
    });

    window.onbeforeunload = function(e) {
        sessionStorage.setItem('scrollpos', window.scrollY);
    };
</script>
"""

# --- Markdown Parsing / Writing ---

def parse_markdown(filepath):
    """Parses markdown into a nested dictionary structure."""
    if not os.path.exists(filepath):
        return []

    lines = []
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    root = []
    stack = [root] 
    last_indent = -1
    node_id_counter = 0

    for line in lines:
        if not line.strip() or not line.strip().startswith('-'):
            continue
        
        raw_indent = len(line) - len(line.lstrip())
        indent_level = raw_indent // 4 

        clean_line = line.strip()[2:]
        link_match = re.match(r'\[(.*?)\]\((.*?)\)', clean_line)
        
        node = {'id': node_id_counter, 'children': []}
        node_id_counter += 1

        if link_match:
            node['type'] = 'link'
            node['title'] = link_match.group(1)
            node['url'] = link_match.group(2)
        else:
            node['type'] = 'folder'
            node['title'] = clean_line
            node['url'] = None

        if indent_level > last_indent:
            if stack[-1]:
                parent = stack[-1][-1]
                stack.append(parent['children'])
            else:
                stack.append(root) 
        elif indent_level < last_indent:
            diff = last_indent - indent_level
            for _ in range(diff):
                if len(stack) > 1: stack.pop()
        
        stack[-1].append(node)
        last_indent = indent_level

    return root

def write_markdown(filepath, data):
    """Writes the data structure back to markdown."""
    lines = []
    
    def recursive_write(nodes, depth):
        indent = "    " * depth
        for node in nodes:
            if node['type'] == 'link':
                lines.append(f"{indent}- [{node['title']}]({node['url']})\n")
            else:
                lines.append(f"{indent}- {node['title']}\n")
                recursive_write(node['children'], depth + 1)

    recursive_write(data, 0)
    
    with LOCK:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines)

# --- Tree Helpers ---

def find_node_by_id(nodes, target_id):
    for node in nodes:
        if node['id'] == target_id:
            return node
        found = find_node_by_id(node['children'], target_id)
        if found: return found
    return None

def delete_node_by_id(nodes, target_id):
    for i, node in enumerate(nodes):
        if node['id'] == target_id:
            del nodes[i]
            return True
        if delete_node_by_id(node['children'], target_id):
            return True
    return False

def move_node_in_tree(nodes, target_id, direction):
    """Swaps a node with its neighbor in the list."""
    for i, node in enumerate(nodes):
        if node['id'] == target_id:
            new_index = i + direction
            if 0 <= new_index < len(nodes):
                nodes[i], nodes[new_index] = nodes[new_index], nodes[i]
                return True
            return False 
        
        if move_node_in_tree(node['children'], target_id, direction):
            return True
    return False

# --- Favicon Logic ---

def get_favicon_filename(url):
    hash_obj = hashlib.md5(url.encode())
    return hash_obj.hexdigest()

def download_favicon(url):
    if not url: return
    filename = get_favicon_filename(url)
    filepath = os.path.join(FAVICONS_DIR, filename + ".ico")
    placeholder_path = os.path.join(FAVICONS_DIR, filename + ".missing")

    if os.path.exists(filepath) or os.path.exists(placeholder_path):
        return

    try:
        r = requests.get(url, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        icon_link = soup.find("link", rel=lambda x: x and 'icon' in x.lower())
        
        icon_url = ""
        if icon_link:
            icon_url = urljoin(url, icon_link['href'])
        else:
            parsed = urlparse(url)
            icon_url = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"

        img_r = requests.get(icon_url, timeout=5)
        if img_r.status_code == 200 and len(img_r.content) > 0:
            with open(filepath, 'wb') as f:
                f.write(img_r.content)
    except:
        with open(placeholder_path, 'w') as f:
            f.write("missing")

def background_favicon_check(bookmarks):
    def traverse(nodes):
        for node in nodes:
            if node['type'] == 'link':
                download_favicon(node['url'])
            traverse(node['children'])
    traverse(bookmarks)

def perform_cleanup_favicons(bookmarks):
    """Deletes files in favicon dir that don't match any current bookmark URL."""
    valid_hashes = set()
    
    def collect_hashes(nodes):
        for node in nodes:
            if node['type'] == 'link':
                valid_hashes.add(get_favicon_filename(node['url']))
            collect_hashes(node['children'])
            
    collect_hashes(bookmarks)
    
    deleted_count = 0
    if os.path.exists(FAVICONS_DIR):
        for filename in os.listdir(FAVICONS_DIR):
            name_part, ext = os.path.splitext(filename)
            if ext in ['.ico', '.missing']:
                if name_part not in valid_hashes:
                    try:
                        os.remove(os.path.join(FAVICONS_DIR, filename))
                        deleted_count += 1
                    except OSError:
                        pass
    return deleted_count

# --- Web Routes ---

@app.route('/')
def index():
    data = parse_markdown(BOOKMARKS_FILE)
    
    html = f"<html><head><title>Bookmarks</title>{HEAD_CONTENT}</head><body>"
    
    # Navigation Header
    html += '<div class="nav-header">'
    html += "<h2>My Bookmarks</h2>"
    html += f'<a href="{url_for("add_step1")}">[+ Add Bookmark]</a> '
    html += f'<a href="{url_for("add_folder")}">[+ Add Folder]</a> '
    html += f'<span style="float:right"><a href="{url_for("cleanup")}" onclick="return confirm(\'Delete unused favicons?\')">[Cleanup Favicons]</a></span>'
    html += "</div>"
    
    # Flash messages
    messages = request.args.get('msg')
    if messages:
         html += f'<div class="flash">{messages}</div>'

    def render_nodes(nodes):
        if not nodes: return ""
        out = "<ul>"
        count = len(nodes)
        for i, node in enumerate(nodes):
            out += "<li>"
            out += '<div class="node-row">'
            
            # Reordering Arrows (Only show valid moves)
            out += '<span class="actions">'
            if i > 0: 
                out += f'<a href="{url_for("move", node_id=node["id"], direction="up")}" class="move-btn" title="Move Up">↑</a>'
            else:
                out += '<span style="display:inline-block; width:14px;"></span>' # Spacer
            
            if i < count - 1:
                out += f'<a href="{url_for("move", node_id=node["id"], direction="down")}" class="move-btn" title="Move Down">↓</a>'
            else:
                out += '<span style="display:inline-block; width:14px;"></span>' # Spacer
            out += '</span>'

            # Icon & Content
            if node['type'] == 'link':
                fname = get_favicon_filename(node['url']) + ".ico"
                if os.path.exists(os.path.join(FAVICONS_DIR, fname)):
                    out += f'<img src="/favicons/{fname}" class="favicon">'
                else:
                    out += '<span class="placeholder-icon"></span>'

                out += f'<a href="{node["url"]}" target="_blank" class="main-link">{node["title"]}</a>'
            else:
                out += f'<span class="folder">{node["title"]}</span>'

            # Edit/Delete
            out += f'<span class="actions"> <a href="{url_for("edit", node_id=node["id"])}">[edit]</a> <a href="{url_for("delete", node_id=node["id"])}" onclick="return confirm(\'Delete?\')">[del]</a>'
            
            # Add Sub-items (if folder)
            if node['type'] == 'folder':
                out += f' | <a href="{url_for("add_step1", parent_id=node["id"])}">[+link]</a>'
                out += f' <a href="{url_for("add_folder", parent_id=node["id"])}">[+folder]</a>'
            
            out += "</span></div>"
            out += render_nodes(node['children'])
            out += "</li>"
        out += "</ul>"
        return out

    html += render_nodes(data)
    html += "</body></html>"
    return html

@app.route('/favicons/<path:filename>')
def serve_favicon(filename):
    return send_from_directory(FAVICONS_DIR, filename)

@app.route('/cleanup')
def cleanup():
    data = parse_markdown(BOOKMARKS_FILE)
    count = perform_cleanup_favicons(data)
    return redirect(url_for('index', msg=f"Cleaned up {count} unused favicon files."))

@app.route('/move/<int:node_id>/<direction>')
def move(node_id, direction):
    data = parse_markdown(BOOKMARKS_FILE)
    dir_val = -1 if direction == 'up' else 1
    if move_node_in_tree(data, node_id, dir_val):
        write_markdown(BOOKMARKS_FILE, data)
    return redirect(url_for('index'))

@app.route('/add', methods=['GET', 'POST'])
def add_step1():
    parent_id = request.args.get('parent_id')
    if request.method == 'POST':
        url = request.form['url']
        parent_id = request.form.get('parent_id')
        
        title = "New Bookmark"
        try:
            r = requests.get(url, timeout=5)
            soup = BeautifulSoup(r.text, 'html.parser')
            if soup.title:
                title = soup.title.string.strip()
        except:
            pass
        
        return render_template_string("""
            <html><head><title>Confirm</title>{{ css|safe }}</head><body>
            <h3>Confirm Bookmark Details</h3>
            <form action="{{ url_for('add_step2') }}" method="post">
                <input type="hidden" name="parent_id" value="{{ parent_id }}">
                <label>URL:</label><br>
                <input type="text" name="url" value="{{ url }}"><br>
                <label>Title:</label><br>
                <input type="text" name="title" value="{{ title }}"><br>
                <button type="submit">Save Bookmark</button>
            </form>
            </body></html>
        """, css=HEAD_CONTENT, url=url, title=title, parent_id=parent_id if parent_id else "")
    
    return f"""
    <html><head><title>Add Link</title>{HEAD_CONTENT}</head><body>
    <h3>Add New Bookmark</h3>
    <form method="post">
        <input type="hidden" name="parent_id" value="{parent_id if parent_id else ''}">
        <input type="text" name="url" placeholder="http://..." required autofocus>
        <button type="submit">Next</button>
    </form>
    </body></html>
    """

@app.route('/add/save', methods=['POST'])
def add_step2():
    url = request.form['url']
    title = request.form['title']
    parent_id = request.form.get('parent_id')
    
    data = parse_markdown(BOOKMARKS_FILE)
    new_node = {'type': 'link', 'title': title, 'url': url, 'children': [], 'id': 999} 

    if parent_id and parent_id != "None" and parent_id != "":
        parent = find_node_by_id(data, int(parent_id))
        if parent:
            parent['children'].append(new_node)
        else:
            data.append(new_node)
    else:
        data.append(new_node)

    write_markdown(BOOKMARKS_FILE, data)
    threading.Thread(target=download_favicon, args=(url,)).start()
    return redirect(url_for('index'))

@app.route('/add_folder', methods=['GET', 'POST'])
def add_folder():
    parent_id = request.args.get('parent_id')
    
    if request.method == 'POST':
        title = request.form['title']
        p_id = request.form.get('parent_id')
        
        data = parse_markdown(BOOKMARKS_FILE)
        new_node = {'type': 'folder', 'title': title, 'url': None, 'children': [], 'id': 999}
        
        if p_id and p_id != "None" and p_id != "":
            parent = find_node_by_id(data, int(p_id))
            if parent:
                parent['children'].append(new_node)
            else:
                data.append(new_node)
        else:
            data.append(new_node)
            
        write_markdown(BOOKMARKS_FILE, data)
        return redirect(url_for('index'))
        
    return f"""
    <html><head><title>Add Folder</title>{HEAD_CONTENT}</head><body>
    <h3>Add New Folder</h3>
    <form method="post">
        <input type="hidden" name="parent_id" value="{parent_id if parent_id else ''}">
        <input type="text" name="title" placeholder="Folder Name" required autofocus>
        <button type="submit">Add Folder</button>
    </form>
    </body></html>
    """

@app.route('/delete/<int:node_id>')
def delete(node_id):
    data = parse_markdown(BOOKMARKS_FILE)
    if delete_node_by_id(data, node_id):
        write_markdown(BOOKMARKS_FILE, data)
    return redirect(url_for('index'))

@app.route('/edit/<int:node_id>', methods=['GET', 'POST'])
def edit(node_id):
    data = parse_markdown(BOOKMARKS_FILE)
    node = find_node_by_id(data, node_id)
    
    if not node:
        return redirect(url_for('index'))

    if request.method == 'POST':
        node['title'] = request.form['title']
        if node['type'] == 'link':
            node['url'] = request.form['url']
            threading.Thread(target=download_favicon, args=(node['url'],)).start()
            
        write_markdown(BOOKMARKS_FILE, data)
        return redirect(url_for('index'))

    form_fields = f'<label>Title</label><br><input type="text" name="title" value="{node["title"]}"><br>'
    if node['type'] == 'link':
        form_fields += f'<label>URL</label><br><input type="text" name="url" value="{node["url"]}"><br>'

    return f"""
    <html><head><title>Edit</title>{HEAD_CONTENT}</head><body>
    <h3>Edit</h3>
    <form method="post">
        {form_fields}
        <button type="submit">Save Changes</button>
    </form>
    </body></html>
    """

# --- Main Entry Point ---

def main():
    global BOOKMARKS_FILE, FAVICONS_DIR
    
    parser = argparse.ArgumentParser(description="Markdown Bookmark Manager")
    parser.add_argument("file", help="Path to the bookmarks.md file")
    args = parser.parse_args()

    BOOKMARKS_FILE = os.path.abspath(args.file)
    base_dir = os.path.dirname(BOOKMARKS_FILE)
    FAVICONS_DIR = os.path.join(base_dir, "favicons")

    if not os.path.exists(BOOKMARKS_FILE):
        with open(BOOKMARKS_FILE, 'w') as f:
            f.write("")

    if not os.path.exists(FAVICONS_DIR):
        os.makedirs(FAVICONS_DIR)

    print("Starting background favicon check...")
    initial_data = parse_markdown(BOOKMARKS_FILE)
    threading.Thread(target=background_favicon_check, args=(initial_data,)).start()

    print(f"Serving bookmarks from {BOOKMARKS_FILE}")
    print("Go to http://127.0.0.1:5000")
    
    app.run(port=5000, debug=False)

if __name__ == '__main__':
    main()

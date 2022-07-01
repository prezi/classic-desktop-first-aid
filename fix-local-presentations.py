#!/usr/bin/env python3
#
# Copyright (c) 2021-2022 Prezi.com
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import datetime
import hashlib
import os
import plistlib
import random
import shutil
import string
import subprocess
import sys
import xml.etree.ElementTree as etree


def old_hash(url):
    data = dict()
    data["$version"] = 100000
    data["$objects"] = ["$null", url]
    data["$archiver"] = "NSKeyedArchiver"
    data["$top"] = dict(root=plistlib.UID(1))

    plist = plistlib.dumps(data, fmt=plistlib.FMT_BINARY, sort_keys=False)
    return hashlib.md5(plist).hexdigest().upper()


def new_hash(url):
    data = dict()
    data["$version"] = 100000
    data["$archiver"] = "NSKeyedArchiver"
    data["$top"] = dict(root=plistlib.UID(1))
    data["$objects"] = ["$null", url]

    plist = plistlib.dumps(data, fmt=plistlib.FMT_BINARY, sort_keys=False)
    return hashlib.md5(plist).hexdigest().upper()


def extract_local_urls(path):
    et = etree.parse(path)
    root = et.getroot()
    result = []
    obj_types = {"image", "video"}

    for obj in root.findall(".zui-table/object"):
        if "type" not in obj.attrib or obj.attrib["type"] not in obj_types:
            continue

        url = obj.findall("./source/url")
        if len(url) != 1:
            continue

        url = url[0].text
        if not url.startswith("//prezi-local/"):
            continue

        result.append(url)

    return result


def fix_cache(content_dir):
    content_xml_path = os.path.join(content_dir, "content.xml")
    if not os.path.exists(content_xml_path):
        return False

    urls = extract_local_urls(content_xml_path)
    file_pairs = set()

    for url in urls:
        old_fn = old_hash(url)
        new_fn = new_hash(url)
        old_path = os.path.join(content_dir, "repos", old_fn[:2], old_fn)
        new_path = os.path.join(content_dir, "repos", new_fn[:2], new_fn)
        file_pairs.add((old_path, new_path))

    if len(file_pairs) == 0:
        return False

    missing = []
    to_move = []
    for old_path, new_path in file_pairs:
        if os.path.exists(new_path):
            continue

        if not os.path.exists(old_path):
            missing.append(old_path)
            continue

        to_move.append((old_path, new_path))

    if len(to_move) > 0:
        print(f"Fixing cache in {content_dir}")
        for old_path, new_path in to_move:
            old_path_info = os.path.relpath(old_path, content_dir)
            new_path_info = os.path.relpath(new_path, content_dir)

            new_dir = os.path.dirname(new_path)
            if not os.path.exists(new_dir):
                os.makedirs(new_dir)

            print(f"- Moving {old_path_info} to {new_path_info}")
            shutil.move(old_path, new_path)

    return len(to_move) > 0


def is_flv_file(path):
    with open(path, "rb") as fp:
        return fp.read(3) == b'FLV'


def validate_backup_id(backup_id):
    return len(backup_id) == 28


def find_backups(content_dir):
    result = []
    files = next(os.walk(content_dir))[2]
    prefix = "backup-"
    ext = ".xml"
    for item in files:
        if item.startswith(prefix) and item.endswith(ext):
            backup_id = item[len(prefix):][:-len(ext)]
            if validate_backup_id(backup_id):
                result.append(backup_id)

    return result


def fix_content_xml(content_dir, backup_id):
    content_xml_path = os.path.join(content_dir, "content.xml")
    if not os.path.exists(content_xml_path):
        return False

    backup_xml_path = os.path.join(content_dir, f"backup-{backup_id}.xml")
    if os.path.exists(backup_xml_path):
        print(f"warning: backup file to be used already exists in {content_dir}")
        return False

    et = etree.parse(content_xml_path)
    root = et.getroot()
    obj_types = {"image", "video"}

    zui_table = root.find(".zui-table")
    removed_ids = set()
    changes = []
    for obj in zui_table.findall("object"):
        if "type" not in obj.attrib or obj.attrib["type"] not in obj_types:
            continue

        url = obj.find("./source/url")
        if url is None:
            continue

        url = url.text
        if not url.startswith("//prezi-local/"):
            continue

        url_hash = new_hash(url)
        file_path = os.path.join(content_dir, "repos", url_hash[:2], url_hash)

        if os.path.exists(file_path) and not is_flv_file(file_path):
            continue

        if "id" in obj.attrib:
            removed_ids.add(obj.attrib["id"])

        changes.append(f"- Removing reference to {url}")
        zui_table.remove(obj)

    path = root.find(".path")
    remove_actions = False

    if path is not None:
        for step in path.findall("s"):
            eagle = step.find("eagle")
            fadein = step.find("buildin")
            eagle_id = eagle.attrib.get("o") if eagle is not None else None
            fadein_id = fadein.attrib.get("o") if fadein is not None else None
            remove = False

            if eagle is not None:
                # Note: we need to remove actions after an eagle was removed
                remove_actions = eagle_id in removed_ids

            if eagle_id in removed_ids:
                remove = True
                changes.append(f"- Removing eagle-to object {eagle_id}")

            if fadein_id in removed_ids:
                remove = True
                changes.append(f"- Removing fade-in object {fadein_id}")

            if remove or remove_actions:
                if not remove:
                    changes.append("- Implicitly removing path action")
                path.remove(step)

    if len(changes) > 0:
        if not os.path.exists(backup_xml_path):
            print(f"Creating backup xml {backup_xml_path}")
            shutil.copy2(content_xml_path, backup_xml_path)

        print(f"Patching {content_xml_path}")
        for line in changes:
            print(line)
        with open(content_xml_path, "wb") as fp:
            et.write(fp, encoding="us-ascii")

    return len(changes) > 0


def find_content_dirs():
    home_dir = os.path.expanduser("~")
    app_dir = os.path.join(
        home_dir, "Library", "Application Support", "com.prezi.desktop")

    for root, dirs, files in os.walk(app_dir):
        if "content.xml" in files:
            yield root


def require_python_version(version):
    if version > sys.version_info:
        expected = ".".join(map(str, version))
        actual = ".".join(map(str, sys.version_info[:3]))
        print(f"error: unsupported Python version: {actual}")
        print(f"       at least Python {expected} is required\n")
        sys.exit(1)


def require_catalina():
    if sys.platform != "darwin":
        print("error: only macOS is supported")
        sys.exit(1)
    try:
        result = subprocess.check_output(["sw_vers", "-productVersion"]).decode()
    except:
        print("error: could not check macOS version")
        sys.exit(1)

    if tuple(map(int, result.split("."))) < (10, 15):
        print("error: this script requires at least macOS 10.15 to run")
        sys.exit(1)


def show_restore_all():
    backups = []
    executable = os.path.basename(sys.argv[0])

    for content_dir in find_content_dirs():
        backups += find_backups(content_dir)

    if len(backups) == 0:
        return

    backups.sort()
    if len(backups) == 1:
        print(
            f"* If you need to restore your presentations, please run:\n")
    else:
        print(
            f"* If you need to restore your presentations, please run one of these commands:\n")

    for item in backups:
        print(f"  python3 {executable} {item}")

    print()


def show_restore(backup_id):
    executable = os.path.basename(sys.argv[0])
    print(
        f"\n* Your presentation(s) have changed!\n"
        f"* To restore the previous state of your presentation(s), please run:\n\n"
        f"  python3 {executable} {backup_id}\n")


def generate_backup_id():
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d--%H-%M-%S")
    random_id = "".join([random.choice(string.ascii_lowercase) for i in range(6)])
    return f"{timestamp}--{random_id}"


def run_fixes():
    changed_cache = False
    changed_content = False
    backup_id = generate_backup_id()
    backups = []

    for content_dir in find_content_dirs():
        changed_cache |= fix_cache(content_dir)
        changed_content |= fix_content_xml(content_dir, backup_id)
        backups += find_backups(content_dir)

    if changed_content:
        show_restore(backup_id)

    elif not changed_cache and len(backups) > 0:
        print("* All presentations look good!")
        show_restore_all()


def run_restore(restore_id):
    if not validate_backup_id(restore_id):
        print("error: invalid backup id")
        sys.exit(1)

    changes = False
    for content_dir in find_content_dirs():
        backups = find_backups(content_dir)
        if restore_id not in backups:
            continue

        changes = True
        content_xml_path = os.path.join(content_dir, "content.xml")
        restore_xml_path = os.path.join(content_dir, f"backup-{restore_id}.xml")

        print(f"Restoring content.xml in {content_dir}")
        shutil.copy2(restore_xml_path, content_xml_path)


if __name__ == "__main__":
    # Require python 3.6 - f-strings
    # Require python 3.8 - plistlib.uid

    require_python_version((3, 8))
    require_catalina()

    if len(sys.argv) < 2:
        run_fixes()
    else:
        run_restore(sys.argv[1])

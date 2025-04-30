#!/usr/bin/env python3
"""
FONarchive Manager Script (Patched)

This script manages font files in Adobe’s livetype folder by copying, parsing, renaming, and organizing them into a new FONarchive directory on the user's Desktop or a custom output directory. It is cross-platform, safe, and modular with logging, error handling, and user prompts.

Requirements: Python 3.8+, fontTools>=4.38.0, packaging, tqdm
"""
import os
import sys
import platform
import shutil
import logging
import logging.handlers
import csv
import datetime
import pathlib
import argparse
import subprocess
import re
from tqdm import tqdm
import xml.etree.ElementTree as ET
import getpass

# --- Logging Setup ---
def setup_logging(log_dir: pathlib.Path):
    now = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    base_log_name = f"{now}.txt"
    log_path = log_dir / base_log_name
    unique_id = 1
    while log_path.exists():
        log_path = log_dir / f"{now}_{unique_id}.txt"
        unique_id += 1
    logger = logging.getLogger("FONarchive")
    logger.setLevel(logging.INFO)
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=1, encoding='utf-8')
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
    handler.setFormatter(formatter)
    logger.handlers.clear()
    logger.addHandler(handler)
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.info(f"Logging initialized at {log_path}")
    return logger, log_path

# --- Dependency Check ---
def check_dependencies(logger):
    missing = []
    vparse = None
    # Check packaging
    try:
        import packaging
        try:
            from packaging.version import parse as vparse
        except Exception:
            missing.append('packaging')
    except ImportError:
        missing.append('packaging')
    # Check fontTools
    try:
        import fontTools
        from fontTools import __version__ as ft_ver
        if vparse:
            if vparse(ft_ver) < vparse("4.38.0"):
                missing.append('fontTools>=4.38.0')
        else:
            # Can't check version if packaging missing
            missing.append('fontTools>=4.38.0')
    except ImportError:
        missing.append('fontTools>=4.38.0')
    # Check tqdm
    try:
        import tqdm
    except ImportError:
        missing.append('tqdm')
    if missing:
        print(f"Missing or outdated dependencies: {', '.join(missing)}. Install now? (y/n): ", end='')
        resp = input().strip().lower()
        if resp == 'y':
            pip_cmd = [sys.executable, "-m", "pip", "install"]
            if sys.prefix == getattr(sys, "base_prefix", sys.prefix):
                pip_cmd.append("--user")
            pip_cmd.extend(['"fontTools>=4.38.0"', "packaging", "tqdm"])
            try:
                result = subprocess.run(
                    pip_cmd,
                    capture_output=False,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    logger.error(f"Failed to install dependencies.\nReturn code: {result.returncode}")
                    logger.error(f"Tried command: {' '.join(pip_cmd)}")
                    print("Failed to install dependencies. See log for details.")
                    sys.exit(1)
                else:
                    logger.info("Dependencies installed successfully.")
            except Exception as e:
                logger.error(f"Dependency install failed: {e}")
                print(f"Dependency install failed: {e}")
                sys.exit(1)
        else:
            logger.error("Required dependencies are missing. Exiting.")
            sys.exit(1)
    else:
        return

# --- Username Sanitization ---
def sanitize_username(username: str) -> str:
    username = username.strip()
    if not username or any(x in username for x in ('..', '/', '\\')):
        return ''
    return username

# --- Filename Sanitization ---
def sanitize_filename(name: str, logger=None) -> str:
    # Remove or replace invalid filename characters for cross-platform safety
    # Invalid: < > : " / \ | ? *
    # Replace spaces with underscores
    import re
    if not isinstance(name, str):
        if logger:
            logger.warning(f"sanitize_filename: Non-string input: {name}")
        return "unnamed"
    name = name.strip()
    if not name:
        if logger:
            logger.warning("sanitize_filename: Empty input, using 'unnamed'")
        return "unnamed"
    # Replace spaces with underscores
    name = name.replace(' ', '_')
    # Replace invalid characters with underscores
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Remove consecutive underscores
    name = re.sub(r'_+', '_', name)
    # Strip leading/trailing dots and spaces/underscores
    name = name.strip(' ._')
    # If nothing left, return 'unnamed'
    if not name:
        if logger:
            logger.warning("sanitize_filename: All characters invalid, using 'unnamed'")
        return "unnamed"
    return name

# --- Username Prompt & Path Validation ---
def prompt_account_name(logger):
    sys_platform = platform.system()
    default_username = None
    try:
        default_username = getpass.getuser()
    except Exception:
        pass
    for attempt in range(3):
        prompt = f"Enter your account username"
        if default_username:
            prompt += f" [default: {default_username}]"
        prompt += ": "
        username = input(prompt).strip()
        if not username and default_username:
            username = default_username
        username = sanitize_username(username)
        if username.lower() == 'cancel':
            logger.info("User cancelled username prompt. Exiting.")
            sys.exit(0)
        if not username:
            print("Invalid username. Try again.")
            logger.warning("Rejected invalid username input.")
            continue
        if sys_platform == 'Darwin':
            lt_path = pathlib.Path(f"/Users/{username}/Library/Application Support/Adobe/CoreSync/plugins/livetype")
            desktop_path = pathlib.Path(f"/Users/{username}/Desktop")
        elif sys_platform == 'Windows':
            lt_path = pathlib.Path(f"C:/Users/{username}/AppData/Roaming/Adobe/CoreSync/plugins/livetype")
            desktop_path = pathlib.Path(f"C:/Users/{username}/Desktop")
        else:
            print("Unsupported OS.")
            logger.error("Unsupported OS for livetype path.")
            sys.exit(1)
        if lt_path.exists() and desktop_path.exists():
            logger.info(f"Validated livetype: {lt_path}")
            logger.info(f"Validated Desktop: {desktop_path}")
            return username, lt_path, desktop_path
        else:
            print(f"Could not find livetype or Desktop folder for '{username}'. Attempts left: {2 - attempt}")
            logger.warning(f"Path validation failed for username '{username}'")
    logger.info("User failed to provide valid username after 3 attempts. Exiting.")
    sys.exit(0)

# --- Disk Space Check ---
def check_disk_space(path: pathlib.Path, logger) -> bool:
    usage = shutil.disk_usage(str(path))
    free_gb = usage.free / (1024 ** 3)
    if usage.free < 1 * 1024 * 1024 * 1024:
        logger.warning(f"Low disk space: {free_gb:.2f} GB free on {path.drive if hasattr(path, 'drive') else path}")
        resp = input(f"WARNING: Only {free_gb:.2f} GB free. Continue? (y/n): ").lower()
        if resp != 'y':
            logger.info("User chose not to continue due to low disk space.")
            sys.exit(0)
    logger.info(f"Disk space OK: {free_gb:.2f} GB free on {path}")
    return True

# --- FONarchive Creation ---
def create_fonarchive(desktop_path: pathlib.Path, logger, output_dir: pathlib.Path = None):
    base = output_dir if output_dir else desktop_path / "FONarchive"
    fonarchive = base
    unique_id = 1
    while fonarchive.exists():
        resp = input(f"{fonarchive} exists. Overwrite (o) or use unique name (u)? (o/u): ").lower()
        if resp == 'o':
            shutil.rmtree(fonarchive)
            logger.info(f"Overwrote existing {fonarchive}")
            break
        elif resp == 'u':
            fonarchive = base.parent / f"{base.name}_{unique_id}"
            unique_id += 1
        else:
            print("Invalid input. Try again.")
    fonarchive.mkdir(parents=True, exist_ok=True)
    working = fonarchive / "working"
    done = fonarchive / "DONE"
    working.mkdir(exist_ok=True)
    done.mkdir(exist_ok=True)
    logger.info(f"Created FONarchive at {fonarchive}")
    logger.info(f"Created subfolders: working, DONE")
    return fonarchive, working, done

# --- Move Log File ---
def move_log_to_fonarchive(log_path: pathlib.Path, fonarchive: pathlib.Path, logger):
    dest = fonarchive / log_path.name
    shutil.move(str(log_path), str(dest))
    logger.info(f"Moved log file to {dest}")
    return dest

# --- Clear Working Folder ---
def clear_or_skip_working(working: pathlib.Path, logger):
    if any(working.iterdir()):
        resp = input(f"{working} is not empty. Clear (c) or skip (s)? (c/s): ").lower()
        if resp == 'c':
            for item in working.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            logger.info(f"Cleared {working}")
        else:
            logger.info(f"Skipped clearing {working}")

# --- Hidden File/Folder Handling ---
def is_hidden(filepath: pathlib.Path) -> bool:
    if platform.system() == 'Darwin':
        return filepath.name.startswith('.')
    elif platform.system() == 'Windows':
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x02
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(filepath))
        return bool(attrs & FILE_ATTRIBUTE_HIDDEN)
    return False

def unhide_file_or_folder(filepath: pathlib.Path):
    if platform.system() == 'Darwin':
        if filepath.name.startswith('.'):
            new_name = filepath.name[1:]
            new_path = filepath.parent / new_name
            filepath.rename(new_path)
            return new_path
    elif platform.system() == 'Windows':
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x02
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(filepath))
        if attrs & FILE_ATTRIBUTE_HIDDEN:
            ctypes.windll.kernel32.SetFileAttributesW(str(filepath), attrs & ~FILE_ATTRIBUTE_HIDDEN)
    return filepath

# --- Entitlements XML Parsing ---
def parse_entitlements_xml(livetype: pathlib.Path, logger) -> dict:
    xml_path = livetype / "entitlements.xml"
    font_map = {}
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for font in root.findall(".//font"):
            font_id = font.get("id")
            family_name = font.get("familyName", "")
            full_name = font.get("fullName", "")
            variation_name = font.get("variationName", "") or "Regular"
            is_variable = font.get("isVariable", "false").lower() == "true"
            if font_id is not None and family_name and full_name:
                font_map[font_id] = {
                    "family_name": family_name,
                    "full_name": full_name,
                    "variation_name": variation_name,
                    "is_variable": is_variable
                }
            else:
                logger.error(f"Malformed font entry in entitlements.xml: id={font_id}, family={family_name}, full={full_name}")
    except Exception as e:
        logger.error(f"Failed to parse entitlements.xml: {e}")
        return {}
    return font_map

# --- Font Extension Helper ---
def get_file_extension(file_path: pathlib.Path, logger=None, default_otf=True) -> str:
    try:
        if file_path.stat().st_size < 1024:
            if logger:
                logger.info(f"Ignored {file_path}: File too small")
            return ""
        with open(file_path, 'rb') as f:
            header = f.read(4)
            if header.startswith(b'\x00\x01\x00\x00'):
                return ".ttf"
            elif header.startswith(b'OTTO'):
                return ".otf"
            else:
                if logger:
                    logger.warning(f"No valid magic bytes for {file_path}, defaulting to .otf")
                return ".otf" if default_otf else ""
    except Exception:
        if logger:
            logger.warning(f"No valid magic bytes for {file_path}, defaulting to .otf")
        return ".otf" if default_otf else ""

# --- Copy, Unhide, and Rename Files ---
def copy_and_unhide_all(livetype: pathlib.Path, working: pathlib.Path, logger):
    xml_metadata = parse_entitlements_xml(livetype, logger)
    all_files = [f for f in livetype.rglob('*') if f.is_file()]
    copied_files = []
    ids_seen = set()
    for src in tqdm(all_files, desc="Copying files"):
        rel_path = src.relative_to(livetype)
        parts = list(rel_path.parts)
        for i, part in enumerate(parts):
            if platform.system() == 'Darwin' and part.startswith('.'):
                parts[i] = part[1:]
        dest_path = working.joinpath(*parts)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        orig_stem = src.stem
        xml_id = orig_stem if orig_stem in xml_metadata else None
        if xml_id:
            ext = src.suffix if src.suffix in ('.ttf', '.otf') else get_file_extension(src, logger)
            meta = xml_metadata[xml_id]
            family = meta['family_name'].replace(' ', '_')
            variation = meta['variation_name'].replace(' ', '_')
            new_name_base = f"{family}_{variation}{ext}"
            new_name = new_name_base
            unique_id = 1
            while (dest_path.parent / new_name).exists():
                new_name = f"{family}_{variation}_{unique_id}{ext}"
                unique_id += 1
                logger.warning(f"Warning: Duplicate XML ID {xml_id}")
            new_path = dest_path.parent / new_name
            shutil.copy2(src, new_path)
            logger.info(f"Renamed {rel_path} to {new_name}")
            copied_files.append((new_path, xml_id, rel_path))
            ids_seen.add(xml_id)
        else:
            shutil.copy2(src, dest_path)
            logger.info(f"Copied {rel_path} without renaming: No XML match")
            copied_files.append((dest_path, None, rel_path))
    return copied_files, xml_metadata

# --- Font Family Regex ---
FAMILY_SUFFIXES = r"(?:Bold|Semibold|Italic|Regular|Light|Medium|Black|Thin|Variable|Condensed|Extended|Pro|Display|Capt|Cond|Wide|SmBd|Demi)"
FAMILY_REGEX = re.compile(rf"\\b({FAMILY_SUFFIXES})\\b", re.IGNORECASE)

# --- Font Validation and Metadata Extraction ---
def clean_name(val):
    if isinstance(val, bytes):
        val = val.decode('utf-16-be', errors='ignore') if b'\x00' in val else val.decode('utf-8', errors='ignore')
    if isinstance(val, str):
        val = val.replace('\x00', '').replace('\u0000', '').replace('\u0001', '').replace('\u0002', '').replace('\u0003', '')
        val = val.replace('\u0004', '').replace('\u0005', '').replace('\u0006', '').replace('\u0007', '')
        val = val.replace('\u0008', '').replace('\u0009', '').replace('\u000a', '').replace('\u000b', '').replace('\u000c', '').replace('\u000d', '').replace('\u000e', '').replace('\u000f', '')
        val = val.replace('\x00', '').replace('\x01', '').replace('\x02', '').replace('\x03', '')
        val = val.replace('\x04', '').replace('\x05', '').replace('\x06', '').replace('\x07', '')
        val = val.replace('\x08', '').replace('\x09', '').replace('\x0a', '').replace('\x0b', '').replace('\x0c', '').replace('\x0d', '').replace('\x0e', '').replace('\x0f', '')
        val = val.replace('\u0000', '').replace('\u0001', '').replace('\u0002', '').replace('\u0003', '')
        val = val.replace('\u0004', '').replace('\u0005', '').replace('\u0006', '').replace('\u0007', '')
        val = val.replace('\u0008', '').replace('\u0009', '').replace('\u000a', '').replace('\u000b', '').replace('\u000c', '').replace('\u000d', '').replace('\u000e', '').replace('\u000f', '')
        val = val.encode('ascii', errors='ignore').decode('ascii', errors='ignore')
        val = val.strip()
    return val

def get_base_family(name_table):
    # Try typographic family name (16), else font family name (1)
    fam = name_table.getName(16, 3, 1)
    if not fam:
        fam = name_table.getName(1, 3, 1)
    if not fam:
        fam = name_table.getName(1, 1, 0)
    if fam:
        base = clean_name(fam.string if hasattr(fam, 'string') else fam)
        # Remove weight/style suffixes
        base = FAMILY_REGEX.sub('', base).strip()
        base = re.sub(r'\s+', ' ', base).strip()
        return base
    return 'Unknown'

def detect_font_type(font):
    if 'CFF ' in font or 'CFF2' in font:
        return 'otf'
    return 'ttf'

# --- Magic Bytes for Font Files ---
FONT_MAGIC = [
    (b'\x00\x01\x00\x00', 'ttf'),
    (b'OTTO', 'otf'),
]

SKIPPED_NONFONTS = set()

# --- Parse Fonts ---
def parse_fonts(working: pathlib.Path, logger, xml_metadata: dict, copied_info=None):
    from fontTools.ttLib import TTFont
    font_files = [f for f in working.rglob('*') if f.is_file()]
    metadata_list = []
    rel_to_xml = {}
    xml_processed = set()
    skipped_nonfonts = 0
    if copied_info:
        for f, xml_id, rel_path in copied_info:
            if xml_id:
                rel_to_xml[f] = xml_id
    for f in tqdm(font_files, desc="Parsing fonts"):
        ext = f.suffix.lower()
        try:
            is_font = False
            if ext in ('.ttf', '.otf'):
                is_font = True
            else:
                try:
                    with open(f, 'rb') as fh:
                        head = fh.read(4)
                        if head.startswith(b'\x00\x01\x00\x00') or head.startswith(b'OTTO'):
                            is_font = True
                except Exception:
                    pass
            if not is_font:
                logger.info(f"Skipped non-font file: {f.name}")
                skipped_nonfonts += 1
                continue
            xml_id = rel_to_xml.get(f, None)
            if xml_id and xml_id in xml_metadata:
                meta = xml_metadata[xml_id]
                font_name = meta.get('full_name', '')
                weight = meta.get('variation_name', '')
                style = 'VARIABLE' if meta.get('is_variable') else meta.get('variation_name', '')
                base_family = meta.get('family_name', '')
                file_type = get_file_extension(f, logger).lstrip('.')
                is_variable = meta.get('is_variable', False)
                logger.info(f"Processed {f.name} as {font_name} {style}")
                xml_processed.add(xml_id)
                metadata = {
                    'current_name': str(f.relative_to(working)),
                    'file_type': file_type,
                    'font_name': font_name or 'Unknown',
                    'weight': weight or '',
                    'style': style or '',
                    'is_variable': is_variable,
                    'base_family': base_family or 'Unknown',
                    'xml_id': xml_id
                }
                metadata_list.append(metadata)
            else:
                try:
                    font = TTFont(str(f), fontNumber=0)
                    is_variable = 'fvar' in font
                    name_table = font['name']
                    font_name = ''
                    weight = ''
                    style = ''
                    for record in name_table.names:
                        val = record.string if hasattr(record, 'string') else record
                        if record.nameID == 1 and not font_name:
                            font_name = clean_name(val)
                        if record.nameID == 2 and not weight:
                            weight = clean_name(val)
                        if record.nameID == 17 == record.nameID:
                            style = clean_name(val)
                    if is_variable:
                        style = 'VARIABLE'
                    file_type = detect_font_type(font)
                    base_family = get_base_family(name_table)
                    logger.info(f"Processed {f.name} as fallback {font_name} {style}")
                    metadata = {
                        'current_name': str(f.relative_to(working)),
                        'file_type': file_type,
                        'font_name': font_name or 'Unknown',
                        'weight': weight or '',
                        'style': style or '',
                        'is_variable': is_variable,
                        'base_family': base_family or 'Unknown',
                        'xml_id': None
                    }
                    metadata_list.append(metadata)
                except Exception as e:
                    logger.error(f"Failed to parse {f.name}: No XML match, fontTools error: {e}")
        except Exception as e:
            logger.error(f"Failed to parse {f}: {e}")
    # Ensure all XML-matched fonts are in metadata_list
    ignored_count = 0
    for xml_id, meta in xml_metadata.items():
        if xml_id not in xml_processed:
            logger.info(f"XML ID {xml_id} not found in working/")
            ignored_count += 1
    log_file = next((h.baseFilename for h in logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler)), None)
    if log_file and os.path.exists(log_file) and os.path.getsize(log_file) >= 10 * 1024 * 1024:
        print("Warning: Log file exceeded 10MB cap.")
    if not metadata_list:
        logger.info("No valid fonts found.")
        print("No valid fonts found.")
        sys.exit(0)
    logger.info(f"Processed {len(metadata_list)} fonts, skipped {skipped_nonfonts} non-fonts, ignored {ignored_count} XML IDs")
    return metadata_list

# --- Rename and Unhide Files ---
def rename_and_unhide_files(metadata_list, working: pathlib.Path, logger):
    new_files = []
    seen_paths = set()
    for meta in tqdm(metadata_list, desc="Renaming fonts"):
        old_path = working / meta['current_name']
        ext = '.' + meta['file_type'] if not meta['file_type'].startswith('.') else meta['file_type']
        # XML-matched: keep as is, skip renaming
        if meta.get('xml_id'):
            if old_path.exists():
                new_files.append({'path': old_path, 'base_family': meta['base_family']})
                seen_paths.add(old_path)
            continue
        # Non-XML: rename
        if meta['font_name'] and meta['style']:
            base_name = f"{meta['font_name']}_{meta['style']}"
        else:
            base_name = f"{meta['font_name']}"
        safe_base = sanitize_filename(base_name)
        new_name = f"{safe_base}{ext}"
        new_path = old_path.parent / new_name
        unique_id = 1
        while new_path.exists() and new_path != old_path:
            logger.info(f"Duplicate rename for {old_path}, using {new_name}")
            new_name = f"{safe_base}_{unique_id}{ext}"
            new_path = old_path.parent / new_name
            unique_id += 1
        try:
            if old_path.exists() and old_path != new_path:
                old_path.rename(new_path)
                logger.info(f"Renamed {old_path} to {new_path}")
            new_files.append({'path': new_path, 'base_family': meta['base_family']})
            seen_paths.add(new_path)
        except Exception as e:
            logger.error(f"Critical error: Failed to rename {old_path}: {e}")
            resp = input(f"Critical error: Failed to rename {old_path}. Continue? (y/n): ").strip().lower()
            if resp != 'y':
                logger.error("User aborted due to rename failure.")
                sys.exit(1)
    # Cleanup: delete any files left in working/ not in new_files
    for subdir, _, files in os.walk(working):
        for fname in files:
            fpath = pathlib.Path(subdir) / fname
            if fpath not in seen_paths:
                try:
                    fpath.unlink()
                    logger.info(f"Cleaned up {fpath.parent}: Removed {fname}")
                except Exception as e:
                    logger.error(f"Failed to remove {fpath}: {e}")
    return new_files

# --- Write Metadata CSV ---
def write_metadata_csv(metadata_list, fonarchive: pathlib.Path, logger):
    csv_path = fonarchive / "metadata.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=[
            'current_name', 'file_type', 'font_name', 'weight', 'style', 'is_variable', 'base_family', 'xml_id'], quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for row in metadata_list:
            writer.writerow(row)
    logger.info(f"Wrote metadata CSV to {csv_path}")

# --- Organize Files ---
def organize_files(new_files, done: pathlib.Path, logger):
    for f in tqdm(new_files, desc="Organizing fonts"):
        family_folder = done / sanitize_filename(f['base_family'])
        family_folder.mkdir(exist_ok=True)
        dest = family_folder / f['path'].name
        unique_id = 1
        while dest.exists():
            dest = family_folder / f"{f['path'].stem}_{unique_id}{f['path'].suffix}"
            unique_id += 1
        try:
            shutil.move(str(f['path']), str(dest))
            logger.info(f"Moved {f['path'].name} to {family_folder}/")
        except Exception as e:
            logger.error(f"Failed to move {f['path']} to {dest}: {e}")

# --- Main Entry ---
def main():
    parser = argparse.ArgumentParser(description="FONarchive Manager Script")
    parser.add_argument('--output-dir', type=str, default=None, help='Custom output directory (default: Desktop)')
    args = parser.parse_args()
    temp_log_dir = pathlib.Path.cwd()
    logger, log_path = setup_logging(temp_log_dir)
    check_dependencies(logger)
    username, livetype, desktop = prompt_account_name(logger)
    check_disk_space(desktop, logger)
    output_dir = pathlib.Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    fonarchive, working, done = create_fonarchive(desktop, logger, output_dir)
    move_log_to_fonarchive(log_path, fonarchive, logger)
    clear_or_skip_working(working, logger)
    copied_files, xml_metadata = copy_and_unhide_all(livetype, working, logger)
    metadata_list = parse_fonts(working, logger, xml_metadata, copied_files)
    write_metadata_csv(metadata_list, fonarchive, logger)
    new_files = rename_and_unhide_files(metadata_list, working, logger)
    organize_files(new_files, done, logger)
    print("All done! See your FONarchive folder.")
    logger.info("Script finished successfully.")

if __name__ == '__main__':
    main()

# FONarchive Manager

## A Note from the Author
Hi! This is my first attempt at a Python script. TBH, I don't know Python at all. This was created as an experiment using Windsurf AI IDE with ChatGPT 4.1 as the AI model. I used Grok 3 Beta to organize the logic and write the prompts, which I then fed to GPT through Windsurf to actually write the code. Take a run with the script and let me know what you think. I'm open to suggestions and feedback. See support section below for contact info for bug reports and feature requests.

## Overview
FONarchive Manager is a cross-platform Python script that safely extracts, organizes, and archives font files from Adobe’s livetype folder. It recovers TTF/OTF fonts—including those with non-standard or hidden names (e.g., `.200567`)—used by Adobe Creative Cloud, without modifying the source folder. Fonts are processed and organized in a user-friendly FONarchive directory on your Desktop or a custom location.

**Key Features:**
- Safe: Read-only access to livetype; all changes occur in FONarchive.
- Comprehensive: Handles hidden folders and non-standard font names.
- Organized: Renames fonts (e.g., Arial_Bold_Italic.ttf) and sorts by family.
- User-Friendly: Progress bars, clear prompts, and detailed logging.
- Flexible: Supports custom output paths via `--output-dir`.
- Robust: Validates fonts, handles errors, and resolves naming conflicts.

## Requirements
- Python 3.8 or newer
- Packages: `fontTools>=4.38.0`, `packaging`, `tqdm`

The script will automatically attempt to install `fontTools>=4.38.0`, `packaging`, and `tqdm` if any are missing or outdated. Automatic installation uses `--user` for non-virtual environments and has a 60-second timeout, which may fail on slow networks.

To install manually:
```bash
pip install --user "fontTools>=4.38.0" packaging tqdm
```

## Installation
- Extract `fonarchive_manager.py` to your desired directory.
- Verify Python 3.8+ is installed:
  ```bash
  python --version
  ```
- Install dependencies (if not using the script’s prompt):
  ```bash
  pip install --user "fontTools>=4.38.0" packaging tqdm
  ```

## Usage

Run the script with Python:
```bash
python fonarchive_manager.py
```
Or, with executable permissions:
```bash
./fonarchive_manager.py
```

### Command-Line Options
- `--output-dir <path>`: Specify a custom output directory (default: Desktop/FONarchive).
- Example: `python fonarchive_manager.py --output-dir ~/Documents/FontBackups`

### Steps
1. Enter your account username (case-sensitive) to locate livetype. Type `cancel` to exit, or the script exits after three invalid attempts.
2. Respond to prompts for:
   - Overwriting existing FONarchive (or use a unique name).
   - Clearing the working directory if non-empty.
   - Continuing with low disk space (<1GB free).

## How It Works

The script processes fonts in several stages, ensuring safe and organized output. Below are the key steps:

### Copy Files
- Recursively copies all files from Adobe’s livetype directory.
- **Hidden File/Folder Handling:**
  - On macOS: Renames files/folders starting with a dot (e.g., `.200567` to `200567`).
  - On Windows: Uses system calls to remove the hidden attribute.
- Resolves duplicate names by appending a unique identifier.

### Parse Fonts
- Validates fonts using magic bytes (`\x00\x01\x00\x00` for TTF, `OTTO` for OTF).
- Skips files smaller than 1024 bytes.
- Extracts metadata from `entitlements.xml` when available, or uses fontTools as a fallback.
- Logs all actions, errors, and ignored files.

### Rename and Organize
- Renames fonts for clarity (e.g., `Arial_Bold_Italic.ttf`).
- Organizes fonts by family in the `DONE` subfolder.
- Cleans up any unprocessed files in `working`.

## Output
- **FONarchive Directory:** Contains all processed fonts, organized by family.
- **metadata.csv:** Lists all processed fonts with columns:
  - `current_name`
  - `file_type`
  - `font_name`
  - `weight`
  - `style`
  - `is_variable`
  - `base_family`
  - `xml_id`
- **Example metadata.csv entry:**
  ```plaintext
  "r/200567","ttf","Arial","Bold","Italic","False","Arial","200567"
  ```
- **Log File:** Named `YYYY-MM-DD_HH-MM-SS.txt` (or with a unique suffix if duplicate), initially created in the current working directory, then moved to `FONarchive`.

## Troubleshooting
- **No files found in livetype:**
  - Verify your username (case-sensitive) and ensure livetype contains files.
- **No valid fonts found:**
  - Confirm livetype has TTF/OTF fonts (even with names like `.200567`).
- **Dependency errors:**
  - Allow the script to install dependencies, or run `pip install --user "fontTools>=4.38.0" packaging tqdm`.
  - Automatic installation uses `--user` for non-virtual environments and may fail on slow/offline networks (60-second timeout).
- **Low disk space:**
  - Free up space or use `--output-dir` to a different drive.
- **Permission errors:**
  - Ensure read access to livetype and write access to the output directory.
- **Corrupted fonts:**
  - Invalid fonts are skipped; check the log for details.
- **Naming conflicts:**
  - Duplicate names are resolved with `_1`, `_2`, etc. (e.g., Arial_Bold_Italic_1.ttf).
- **Log file:**
  - Find errors in `FONarchive/YYYY-MM-DD_HH-MM-SS.txt`.
- **Windows hidden file issues:**
  - Check the log for `ctypes`-related errors if hidden file operations fail.

## Notes
- **Safety:** livetype is read-only, and paths are sanitized to prevent unsafe operations.
- **Edge Cases:**
  - Handles hidden folders/files (e.g., `.r`/`.200567`).
  - Resolves naming conflicts with unique suffixes.
  - Exits gracefully if livetype is empty or has no valid fonts.
- **Logs:** Capped at 10MB with one backup to prevent disk issues.
- Compatible with macOS and Windows.

## License
MIT License. Provided as-is for personal and educational use. Not affiliated with Adobe.

## Support
This is a standalone script. For issues or suggestions, check the log file or contact the author if a repository is provided. You can contact me through GIThub or on Telegram: @mickjayofficial 

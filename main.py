import os
import json
import git # New import for GitPython
import time
import threading
import requests
import pprint
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, render_template_string, request, Response, send_file, redirect, url_for
from flask_cors import CORS # Assuming you meant to use CORS based on previous context, even if not explicitly in this snippet
from growattServer import GrowattApi
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import pytz # Import pytz for timezone handling if needed, though not directly used in the provided snippet beyond comments

# --- Configuration and Environment Variables ---
# General
DEBUG_MODE = os.getenv("FLASK_DEBUG", "False").lower() == "true"
HOST_IP = os.getenv("HOST_IP", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000)) # Changed to 8000 as per your app.run()

# Growatt API Credentials
GROWATT_USERNAME = os.getenv("GROWATT_USERNAME", "vospina") # Use env var or default
GROWATT_PASSWORD = os.getenv("GROWATT_PASSWORD", "Vospina.2025") # Use env var or default (consider removing hardcoded defaults for security)
PLANT_ID = os.getenv("PLANT_ID", "2817170") # Use env var or default
STORAGE_SN = os.getenv("STORAGE_SN", "BNG7CH806N") # Use env var or default
PASSWORD_CRC = os.getenv("GROWATT_PASSWORD_CRC", "0c4107c238d57d475d4660b07b2f043e") # Use env var or default

# Telegram Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7653969082:AAGJ_8TL2-MA0uCLgt8UAyfEBRzCmFWyzG") # Use env var or default
CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS", "5715745951").split(',') # Split by comma if multiple IDs, handle as list
chat_log = set()

# GitHub Sync Config
GITHUB_REPO_URL = os.getenv("GITHUB_REPO_URL", "github.com/sjimenezn/growatt2.git")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "sjimenezn")
GITHUB_TOKEN = os.getenv("GITHUB_PAT") # Retrieve PAT from environment variable for security.

GIT_PUSH_INTERVAL_MINS = int(os.getenv("GIT_PUSH_INTERVAL_MINS", "30")) # Sync every 30 minutes
LOCAL_REPO_PATH = os.getenv("LOCAL_REPO_PATH", ".") # Current directory where main.py and saved_data.json reside

# Data file paths (defined after LOCAL_REPO_PATH)
data_file = os.path.join(LOCAL_REPO_PATH, 'saved_data.json')
TEST_DATA_FILE = os.path.join(LOCAL_REPO_PATH, 'saved_data_test.json')

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# --- Global Variables ---
g_repo = None # Global variable for the Git Repo object, initialized by the sync thread
telegram_enabled = False # Global flag to control Telegram bot state
updater = None  # Global reference for the Updater object
dp = None       # Global reference for the Dispatcher object

# --- Growatt API Setup ---
HEADERS = {
    'User-Agent': 'Mozilla/5.5', # User-Agent to mimic a browser
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'X-Requested-With': 'XMLHttpRequest'
}
session = requests.Session() # Persistent session for Growatt API calls

# GrowattApi instance
api = GrowattApi()
api.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148' # Mobile User-Agent for GrowattApi
})

# --- Shared Data ---
current_data = {}
last_processed_time = "Never" # Time of last loop iteration
last_successful_growatt_update_time = "Never" # Time of last *fresh* data received from Growatt API
last_saved_sensor_values = {} # Stores the last successfully saved sensor values for comparison

console_logs = [] # Stores recent console messages for display

# --- Logging and Utility Functions ---
def log_message(message, level="INFO"):
    """Prints a timestamped log message and stores it in console_logs."""
    timestamp = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S") # UTC-5 for Colombia
    log_entry = f"{timestamp} - {level}: {message}"
    print(log_entry)
    console_logs.append((time.time(), log_entry))
    # Keep only logs from the last 6000 seconds (100 minutes)
    now = time.time()
    console_logs[:] = [(t, m) for t, m in console_logs if now - t < 6000]

def send_telegram_message(message):
    """Sends a message to configured Telegram chat IDs if the bot is enabled."""
    global updater
    if telegram_enabled and updater and updater.running:
        for chat_id in CHAT_IDS:
            for attempt in range(3):
                try:
                    updater.bot.send_message(chat_id=chat_id, text=message)
                    log_message(f"✅ Message sent to {chat_id}")
                    break
                except Exception as e:
                    log_message(f"❌ Attempt {attempt + 1} failed to send message to {chat_id}: {e}", level="ERROR")
                    time.sleep(5)
                    if attempt == 2:
                        log_message(f"❌ Failed to send message to {chat_id} after 3 attempts", level="ERROR")
    else:
        log_message(f"Telegram not enabled or updater not running. Message not sent: {message}", level="WARNING")

def get_today_date_utc_minus_5():
    """Returns today's date formatted as YYYY-MM-DD in UTC-5."""
    now = datetime.utcnow() - timedelta(hours=5)
    return now.strftime('%Y-%m-%d')

def growatt_login2():
    """Performs a specific Growatt login using requests session."""
    data = {
        'account': GROWATT_USERNAME,
        'password': '', # Password is sent as CRC, not plain text here
        'validateCode': '',
        'isReadPact': '0',
        'passwordCrc': PASSWORD_CRC
    }
    try:
        response = session.post('https://server.growatt.com/login', headers=HEADERS, data=data)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        log_message("✅ Growatt secondary login successful.")
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Growatt secondary login failed: {e}", level="ERROR")

# --- Git Helper Functions ---
def init_and_add_remote(repo_path, remote_url, username, token):
    """
    Initializes a git repo if not exists and sets up remote.
    Returns the git.Repo object on success, None on failure.
    """
    repo = None
    try:
        try:
            repo = git.Repo(repo_path)
            log_message("✅ Local directory is already a Git repository.")
        except git.InvalidGitRepositoryError:
            log_message("🔄 Initializing new Git repository...")
            repo = git.Repo.init(repo_path)
            log_message("✅ Git repository initialized.")

        if repo is None:
            raise Exception("Failed to initialize or get Git repository object during init_and_add_remote.")

        remote_name = "origin"
        configured_remote_url = f"https://{username}:{token}@{remote_url}"

        if remote_name in repo.remotes:
            log_message(f"🔄 Updating existing remote '{remote_name}' URL with PAT.")
            with repo.remotes[remote_name].config_writer as cw:
                cw.set("url", configured_remote_url)
        else:
            log_message(f"🔄 Adding new remote '{remote_name}' with URL: {configured_remote_url.replace(token, '************')}")
            repo.create_remote(remote_name, configured_remote_url)

        # Always fetch after ensuring remote is set up
        log_message("Fetching from remote...")
        repo.git.fetch()

        # Ensure 'main' branch exists and is checked out/tracking
        if 'main' not in repo.heads:
            log_message("🔄 Local 'main' branch not found, attempting to create and checkout 'origin/main'.")
            try:
                repo.git.checkout('-b', 'main', 'origin/main')
                log_message("✅ Created and checked out 'main' tracking 'origin/main'.")
            except git.exc.GitCommandError as e:
                log_message(f"❌ Failed to create and checkout 'main' tracking 'origin/main': {e.stderr.strip() if e.stderr else str(e)}", level="ERROR")
                # Fallback: if origin/main doesn't exist, create an orphan main branch
                log_message("Attempting to create an orphan 'main' branch as fallback.")
                try:
                    repo.git.checkout('--orphan', 'main')
                    repo.git.rm('-rf', '.') # Remove all files from previous branch (if any)
                    repo.git.commit('--allow-empty', '-m', 'Initial commit for orphan branch')
                    log_message("✅ Created and checked out an empty 'main' branch.")
                except git.exc.GitCommandError as e_orphan:
                    log_message(f"❌ FATAL: Could not create even an orphan 'main' branch: {e_orphan.stderr.strip() if e_orphan.stderr else str(e_orphan)}", level="FATAL")
                    return None
        else:
            if repo.active_branch.name != 'main':
                log_message("🔄 Local 'main' branch exists, switching to it.")
                repo.git.checkout('main')

            try:
                # Check if 'main' is tracking 'origin/main'
                stdout_str = repo.git.rev_parse('--abbrev-ref', '--symbolic-full-name', 'main@{u}')
                if stdout_str.strip() != 'origin/main':
                    log_message("🔄 Local 'main' branch exists but not tracking 'origin/main', setting tracking branch.")
                    repo.heads.main.set_tracking_branch(repo.remotes.origin.refs.main)
                    log_message("✅ Set local 'main' branch to track 'origin/main'.")
                else:
                    log_message("✅ Local 'main' branch exists and is tracking 'origin/main'.")
            except git.exc.GitCommandError as e:
                log_message(f"⚠️ Could not determine tracking status for 'main': {e.stderr.strip() if e.stderr else str(e)}")
                log_message("🔄 Attempting to set local 'main' branch to track 'origin/main' as fallback.")
                try:
                    repo.heads.main.set_tracking_branch(repo.remotes.origin.refs.main)
                    log_message("✅ Set local 'main' branch to track 'origin/main' (fallback).")
                except Exception as set_e:
                    log_message(f"❌ Failed to set tracking branch for 'main' even with fallback: {set_e}", level="ERROR")
                    # If setting tracking fails, it's a significant issue, but might not be fatal for initial clone
        
        return repo

    except git.exc.GitCommandError as e:
        log_message(f"❌ Git command error during init_and_add_remote: {e.stderr.strip() if e.stderr else str(e)}", level="ERROR")
        return None
    except Exception as e:
        log_message(f"❌ FATAL: Unexpected error during init_and_add_remote: {e}", level="FATAL")
        return None

def _robust_git_pull(repo_obj):
    """Performs a git pull --rebase with error handling."""
    log_message("🔄 Performing robust pull on branch 'main' from 'origin'.")
    if repo_obj is None:
        log_message("Git repository object is not initialized for pull.", level="ERROR")
        return False, "Repo not initialized"

    try:
        # Fetch all remote branches and then rebase the current branch onto origin/main
        repo_obj.git.fetch('origin')
        repo_obj.git.rebase('origin/main')
        log_message("✅ Git pull result: Current branch main is up to date (via rebase).")
        return True, "Success"
    except git.exc.GitCommandError as e:
        error_output = e.stderr.strip() if e.stderr else str(e)
        log_message(f"❌ Git pull --rebase failed: {error_output}", level="ERROR")
        if "conflict" in error_output.lower():
            log_message("⚠️ Rebase conflict detected. Attempting to abort rebase.")
            try:
                repo_obj.git.rebase('--abort')
                log_message("✅ Rebase aborted. Please resolve conflicts manually or try again.")
            except Exception as abort_e:
                log_message(f"❌ Failed to abort rebase: {abort_e}", level="FATAL")
        return False, error_output
    except Exception as e:
        log_message(f"❌ An unexpected error occurred during robust Git pull: {e}", level="ERROR")
        return False, str(e)

def _perform_single_github_sync_operation(repo_obj_param=None):
    """
    Performs a single Git pull/push operation specifically for `saved_data_test.json`.
    This is intended for manual trigger.
    """
    log_message("🔄 Attempting GitHub TEST sync operation (via manual trigger button)...")

    repo = g_repo if repo_obj_param is None else repo_obj_param

    if repo is None:
        log_message("❌ Git repository object is not initialized (repo is None). Cannot perform sync.", level="ERROR")
        return False, "Git repository not initialized."

    if not GITHUB_REPO_URL or not GITHUB_USERNAME or not GITHUB_TOKEN:
        log_message("⚠️ GitHub credentials (URL, username, token) are not fully set. Skipping Git operation.", level="WARNING")
        return False, "GitHub credentials not fully set."

    stashed_changes = False

    try:
        # Ensure we are on the main branch
        current_branch = repo.active_branch.name
        if current_branch != 'main':
            log_message(f"Switching from '{current_branch}' to 'main' branch.")
            repo.git.checkout('main')
            log_message("✅ Switched to 'main' branch.")

        # --- STEP 1: Create or Update saved_data_test.json ---
        if os.path.exists(data_file):
            with open(data_file, 'r') as f_src:
                source_content = f_src.read()
            with open(TEST_DATA_FILE, 'w') as f_dest:
                f_dest.write(source_content)
            log_message(f"✅ Created copy of '{data_file}' as '{TEST_DATA_FILE}'.")
        else:
            log_message(f"⚠️ Source data file '{data_file}' not found. Creating empty '{TEST_DATA_FILE}'.", level="WARNING")
            with open(TEST_DATA_FILE, 'w') as f_dest:
                f_dest.write("[]") # Default to empty JSON array
        
        # --- STEP 2: Stash any existing dirty changes BEFORE pull ---
        if repo.is_dirty(untracked_files=True):
            log_message("🔄 Detected unstaged/untracked changes. Stashing them before pull.")
            try:
                repo.git.stash('save', '--include-untracked', 'Auto-stash for manual test sync')
                stashed_changes = True
                log_message("✅ Changes stashed successfully.")
            except git.exc.GitCommandError as stash_e:
                error_message = stash_e.stderr.strip()
                log_message(f"❌ Error stashing changes: {error_message}", level="ERROR")
                if "BUG: unpack-trees.c" in error_message or "invalid path" in error_message:
                    log_message("⚠️ Detected critical Git internal error during stash. Attempting a hard reset and clean-up to recover.", level="WARNING")
                    try:
                        repo.git.reset('--hard')
                        repo.git.clean('-fdx')
                        log_message("✅ Git state reset to clean. (WARNING: Uncommitted changes were lost).")
                        stashed_changes = False # No stash was successfully created
                    except Exception as reset_e:
                        log_message(f"❌ FATAL: Error during Git state reset after stash failure: {reset_e}. Repository might be unrecoverable.", level="FATAL")
                        return False, f"FATAL: Git state unrecoverable: {reset_e}"
                else:
                    log_message("Proceeding to pull, but it might fail due to unstashed changes (non-BUG error).", level="WARNING")

        # --- STEP 3: Pull the latest changes from GitHub ---
        pull_success, pull_msg = _robust_git_pull(repo)
        if not pull_success:
            return False, f"Git pull failed during manual test sync: {pull_msg}"

        # --- STEP 4: Pop the stash if changes were stashed ---
        if stashed_changes:
            log_message("🔄 Popping stash after successful pull during manual test sync.")
            try:
                repo.git.stash('pop')
                log_message("✅ Stash popped successfully.")
            except git.exc.GitCommandError as pop_e:
                log_message(f"❌ Error popping stash during manual test sync: {pop_e.stderr.strip()}", level="WARNING")
                log_message("⚠️ Manual intervention might be required to resolve stash conflicts. Local changes are preserved in stash list.", level="WARNING")
                pass

        # --- STEP 5: Unstage ALL changes, then stage ONLY saved_data_test.json ---
        log_message("🔄 Resetting index to unstage all changes...")
        repo.git.reset() # This is 'git reset --mixed HEAD', which unstages all changes
        log_message("✅ Index reset. Staging only 'saved_data_test.json'.")
        
        repo.index.add([TEST_DATA_FILE]) # Stage only the test file
        log_message(f"✅ Staged '{TEST_DATA_FILE}'.")

        # Check if there are actual differences in the index for TEST_DATA_FILE compared to HEAD
        diff_has_test_file = False
        for item in repo.index.diff("HEAD"):
            if item.a_path == TEST_DATA_FILE or item.b_path == TEST_DATA_FILE:
                diff_has_test_file = True
                break
        
        if not diff_has_test_file:
            log_message(f"⚙️ No new changes detected in '{TEST_DATA_FILE}' to commit. Skipping commit and push.")
            return True, "No changes to push for test file."

        # --- STEP 6: Commit ONLY saved_data_test.json ---
        commit_message = f"Manual TEST sync of saved_data_test.json: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC-5)"
        repo.index.commit(commit_message)
        log_message(f"✅ Committed changes to '{TEST_DATA_FILE}': '{commit_message}'")

        # --- STEP 7: Push with retries ---
        max_retries = 3
        retry_delay = 2
        for i in range(max_retries):
            push_remote_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@{GITHUB_REPO_URL}"
            log_message(f"🔄 Attempting TEST push to GitHub (Attempt {i+1}/{max_retries})...")
            try:
                repo.git.push(push_remote_url, 'main', '--force-with-lease')
                log_message("✅ Successfully pushed TEST file to GitHub.")
                return True, "Successfully pushed TEST file."

            except git.exc.GitCommandError as push_e:
                error_message = push_e.stderr.strip() if isinstance(push_e.stderr, str) else \
                                push_e.stderr.decode('utf-8').strip() if isinstance(push_e.stderr, bytes) else \
                                str(push_e)
                log_message(f"⚠️ TEST push rejected on attempt {i+1}. Error: {error_message}", level="WARNING")

                if i < max_retries - 1:
                    log_message(f"🔄 Pulling again to resolve issues and retrying TEST push in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    pull_success_retry, pull_msg_retry = _robust_git_pull(repo)
                    if not pull_success_retry:
                        log_message(f"❌ Failed to re-pull during TEST push retry: {pull_msg_retry}. Cannot continue retries.", level="ERROR")
                        break
                else:
                    log_message(f"❌ Max retries reached for TEST push. Last error: {error_message}", level="ERROR")
                    return False, f"Failed to push TEST file after {max_retries} retries: {error_message}"

    except Exception as e:
        log_message(f"❌ An unexpected error occurred during GitHub TEST sync: {e}", level="ERROR")
        return False, f"Unexpected error during TEST sync: {e}"
        
def _perform_regular_github_sync_operation(repo_obj_param=None):
    """
    Helper function to perform regular GitHub synchronization for the main `saved_data.json`.
    This is intended for the scheduled sync.
    """
    log_message("🔄 Attempting GitHub REGULAR sync operation...")

    repo = g_repo if repo_obj_param is None else repo_obj_param

    if repo is None:
        log_message("❌ Git repository object is not initialized (repo is None). Cannot perform REGULAR sync.", level="ERROR")
        return False, "Git repository not initialized."

    if not GITHUB_REPO_URL or not GITHUB_USERNAME or not GITHUB_TOKEN:
        log_message("⚠️ GitHub credentials (URL, username, token) are not fully set. Skipping REGULAR Git operation.", level="WARNING")
        return False, "GitHub credentials not fully set."

    stashed_changes = False

    try:
        # Ensure we are on the main branch
        current_branch = repo.active_branch.name
        if current_branch != 'main':
            log_message(f"Switching from '{current_branch}' to 'main' branch for REGULAR sync.")
            repo.git.checkout('main')
            log_message("✅ Switched to 'main' branch.")

        # --- Stash any existing dirty changes BEFORE pull ---
        if repo.is_dirty(untracked_files=True):
            log_message("🔄 Detected unstaged/untracked changes. Stashing them before pull for REGULAR sync.")
            try:
                repo.git.stash('save', '--include-untracked', 'Auto-stash for regular sync before pull')
                stashed_changes = True
                log_message("✅ Changes stashed successfully.")
            except git.exc.GitCommandError as stash_e:
                error_message = stash_e.stderr.strip()
                log_message(f"❌ Error stashing changes for REGULAR sync: {error_message}", level="ERROR")
                if "BUG: unpack-trees.c" in error_message or "invalid path" in error_message:
                    log_message("⚠️ Detected critical Git internal error during stash. Attempting a hard reset and clean-up to recover.", level="WARNING")
                    try:
                        repo.git.reset('--hard')
                        repo.git.clean('-fdx')
                        log_message("✅ Git state reset to clean. (WARNING: Uncommitted changes were lost).")
                        stashed_changes = False
                    except Exception as reset_e:
                        log_message(f"❌ FATAL: Error during Git state reset after stash failure for REGULAR sync: {reset_e}. Repository might be unrecoverable.", level="FATAL")
                        return False, f"FATAL: Git state unrecoverable for REGULAR sync: {reset_e}"
                else:
                    log_message("Proceeding to pull for REGULAR sync, but it might fail due to unstashed changes.", level="WARNING")

        # --- Pull the latest changes from GitHub ---
        pull_success, pull_msg = _robust_git_pull(repo)
        if not pull_success:
            return False, f"Git pull failed during REGULAR sync: {pull_msg}"

        # --- Pop the stash if changes were stashed ---
        if stashed_changes:
            log_message("🔄 Popping stash after successful pull during REGULAR sync.")
            try:
                repo.git.stash('pop')
                log_message("✅ Stash popped successfully.")
            except git.exc.GitCommandError as pop_e:
                log_message(f"❌ Error popping stash during REGULAR sync: {pop_e.stderr.strip()}", level="WARNING")
                log_message("⚠️ Manual intervention might be required to resolve stash conflicts. Local changes are preserved in stash list.", level="WARNING")
                pass

        # --- Add/Commit ONLY saved_data.json for REGULAR sync ---
        if os.path.exists(data_file):
            # Check if saved_data.json has changes.
            status_output = repo.git.status('--porcelain', data_file).strip()
            if status_output and (status_output.startswith('M ') or status_output.startswith('?? ') or status_output.startswith('A ')):
                repo.index.add([data_file])
                log_message(f"✅ Staged '{data_file}' for REGULAR sync.")
                
                commit_message = f"Auto-update Growatt data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC-5)"
                repo.index.commit(commit_message)
                log_message(f"✅ Committed changes to '{data_file}': '{commit_message}'")
            else:
                log_message(f"⚙️ No new changes detected in '{data_file}' for REGULAR sync. Skipping commit.")
                return True, "No changes to push for regular sync."
        else:
            log_message(f"⚠️ {data_file} not found for REGULAR sync. Cannot commit.", level="WARNING")
            return False, "Data file not found for regular sync."

        # --- Push with retries ---
        max_retries = 3
        retry_delay = 2
        for i in range(max_retries):
            push_remote_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@{GITHUB_REPO_URL}"
            log_message(f"🔄 Attempting REGULAR push to GitHub (Attempt {i+1}/{max_retries})...")
            try:
                repo.git.push(push_remote_url, 'main', '--force-with-lease')
                log_message("✅ Successfully pushed REGULAR changes to GitHub.")
                return True, "Successfully pushed REGULAR changes."

            except git.exc.GitCommandError as push_e:
                error_message = push_e.stderr.strip() if isinstance(push_e.stderr, str) else \
                                push_e.stderr.decode('utf-8').strip() if isinstance(push_e.stderr, bytes) else \
                                str(push_e)
                log_message(f"⚠️ REGULAR push rejected on attempt {i+1}. Error: {error_message}", level="WARNING")

                if i < max_retries - 1:
                    log_message(f"🔄 Pulling again to resolve issues and retrying REGULAR push in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    pull_success_retry, pull_msg_retry = _robust_git_pull(repo)
                    if not pull_success_retry:
                        log_message(f"❌ Failed to re-pull during REGULAR push retry: {pull_msg_retry}. Cannot continue retries.", level="ERROR")
                        break
                else:
                    log_message(f"❌ Max retries reached for REGULAR push. Last error: {error_message}", level="ERROR")
                    return False, f"Failed to push REGULAR changes after {max_retries} retries: {error_message}"

    except Exception as e:
        log_message(f"❌ An unexpected error occurred during GitHub REGULAR sync: {e}", level="ERROR")
        return False, f"Unexpected error during REGULAR sync: {e}"

def sync_github_repo():
    """Scheduled thread to perform Git add, commit, and push operation."""
    log_message(f"Starting scheduled GitHub sync thread. Sync interval: {GIT_PUSH_INTERVAL_MINS} minutes.")

    if not GITHUB_REPO_URL or not GITHUB_USERNAME or not GITHUB_TOKEN:
        log_message("⚠️ GitHub credentials not fully set for scheduled sync. Thread will not run.", level="WARNING")
        return

    global g_repo
    repo = None

    try:
        if not os.path.exists(os.path.join(LOCAL_REPO_PATH, '.git')):
            log_message(f"No .git directory found. Attempting to clone {GITHUB_REPO_URL}...")
            authenticated_clone_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@{GITHUB_REPO_URL}"
            git.Repo.clone_from(authenticated_clone_url, LOCAL_REPO_PATH, branch='main')
            log_message("✅ Repository cloned successfully during startup.")
            repo = git.Repo(LOCAL_REPO_PATH)
        else:
            log_message("Git repository already exists. Ensuring remote is set and pulling latest.")
            repo = init_and_add_remote(LOCAL_REPO_PATH, GITHUB_REPO_URL, GITHUB_USERNAME, GITHUB_TOKEN)

        if repo is None:
            raise Exception("Git repository object is None after initial setup (init_and_add_remote or git.Repo failed).")

        log_message("Ensuring main branch is checked out and pulling latest changes.")
        if repo.active_branch.name != 'main':
             log_message("Switching to 'main' branch for initial pull.")
             repo.git.checkout('main')

        # Initial pull for the main data file
        pull_success, pull_msg = _robust_git_pull(repo)
        if pull_success:
            log_message("✅ Git repository updated with latest changes during startup.")
        else:
            log_message(f"❌ Initial Git pull failed during startup: {pull_msg}. This might lead to push issues.", level="ERROR")

    except Exception as e:
        log_message(f"❌ FATAL: Initial Git clone/pull setup for scheduled sync failed: {e}. Thread disabled.", level="FATAL")
        return

    g_repo = repo # Store the successfully initialized repo object in the global variable

    while True:
        time.sleep(GIT_PUSH_INTERVAL_MINS * 60)
        log_message("Scheduled GitHub sync triggered.")
        _perform_regular_github_sync_operation(g_repo) # Call the REGULAR sync for scheduled updates

# --- Growatt Data Fetching and Processing ---
fetched_data = {} # Stores last raw fetched data for console display

def login_growatt():
    """Logs into Growatt API and fetches initial plant/inverter info."""
    log_message("🔄 Attempting Growatt login...")

    try:
        login_response = api.login(GROWATT_USERNAME, GROWATT_PASSWORD)
        fetched_data['login_response'] = login_response
        user = login_response.get('user', {})
        user_id = user.get('id')
        fetched_data['user_id'] = user_id
        fetched_data['cpower_token'] = user.get('cpowerToken')
        fetched_data['cpower_auth'] = user.get('cpowerAuth')
        fetched_data['account_name'] = user.get('accountName')
        fetched_data['email'] = user.get('email')
        fetched_data['last_login_time'] = user.get('lastLoginTime')
        fetched_data['user_area'] = user.get('area')
        log_message("✅ Login successful!")
    except Exception as e:
        log_message(f"❌ Login failed: {e}", level="ERROR")
        return None, None, None, None

    try:
        plant_info = api.plant_list(user_id)
        fetched_data['plant_info'] = plant_info
        plant_data = plant_info['data'][0] # Assuming only one plant
        plant_id_retrieved = plant_data['plantId'] # Use a temp variable to avoid name clash
        fetched_data['plant_id'] = plant_id_retrieved
        fetched_data['plant_name'] = plant_data['plantName']
        fetched_data['plant_total_data'] = plant_info.get('totalData', {})
    except Exception as e:
        log_message(f"❌ Failed to retrieve plant info: {e}", level="ERROR")
        return None, None, None, None

    try:
        inverter_info = api.inverter_list(plant_id_retrieved)
        fetched_data['inverter_info'] = inverter_info
        inverter_data = inverter_info[0] # Assuming only one inverter
        inverter_sn_retrieved = inverter_data['deviceSn']
        datalog_sn_retrieved = inverter_data.get('datalogSn', 'N/A')
        fetched_data['inverter_sn'] = inverter_sn_retrieved
        fetched_data['datalog_sn'] = datalog_sn_retrieved
        fetched_data['inverter_alias'] = inverter_data.get('deviceAilas')
        fetched_data['inverter_capacity'] = inverter_data.get('capacity')
        fetched_data['inverter_energy'] = inverter_data.get('energy')
        fetched_data['inverter_active_power'] = inverter_data.get('activePower')
        fetched_data['inverter_apparent_power'] = inverter_data.get('apparentPower')
        fetched_data['inverter_status'] = inverter_data.get('deviceStatus')
    except Exception as e:
        log_message(f"❌ Failed to retrieve inverter info: {e}", level="ERROR")
        return None, None, None, None

    try:
        storage_detail = api.storage_detail(inverter_sn_retrieved)
        fetched_data['storage_detail'] = storage_detail
    except Exception as e:
        log_message(f"❌ Failed to retrieve storage detail: {e}", level="ERROR")
        fetched_data['storage_detail'] = {}

    log_message(f"🌿 User ID: {user_id}")
    log_message(f"🌿 Plant ID: {plant_id_retrieved}")
    log_message(f"🌿 Inverter SN: {inverter_sn_retrieved}")
    log_message(f"🌿 Datalogger SN: {datalog_sn_retrieved}")

    return user_id, plant_id_retrieved, inverter_sn_retrieved, datalog_sn_retrieved

def save_data_to_file(data, filename):
    """Saves data to a JSON file, maintaining a list of entries and capping its size."""
    global last_saved_sensor_values
    try:
        existing_data = []
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            with open(filename, "r") as f:
                try:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        log_message(f"⚠️ Warning: {filename} did not contain a JSON list. Attempting to convert.", level="WARNING")
                        # If it's not a list, treat it as a single entry or start fresh
                        existing_data = [existing_data] if existing_data else []
                except json.JSONDecodeError:
                    log_message(f"❌ Error decoding existing JSON from {filename}. File might be corrupted. Starting with empty list.", level="ERROR")
                    existing_data = [] # Reset if corrupted

        # Add the new data point
        existing_data.append(data)

        # Keep only the last 1200 entries (approx 4 days @ ~4.6 min interval)
        existing_data = existing_data[-1200:]

        # Write the entire list back as a single JSON array
        with open(filename, "w") as f:
            # Using compact format for smaller file size, suitable for Git
            json.dump(existing_data, f, indent=None, separators=(',', ':'))

        log_message(f"✅ Saved data to file: {filename} as a JSON array.")

        # After successful save, update last_saved_sensor_values only for the main data file
        if filename == data_file:
            # Only store sensor values that are not None for comparison next time
            comparable_data = {k: v for k, v in data.items() if k != 'timestamp' and v is not None}
            last_saved_sensor_values.update(comparable_data)

    except Exception as e:
        log_message(f"❌ Error saving data to file {filename}: {e}", level="ERROR")

def monitor_growatt():
    """Monitors Growatt data, handles Telegram alerts, and triggers data saving."""
    global last_processed_time, last_successful_growatt_update_time, last_saved_sensor_values
    threshold = 80 # AC input voltage threshold for alerts
    sent_lights_off = False
    sent_lights_on = False

    loop_counter = 0

    user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None

    # On startup, attempt to populate last_saved_sensor_values from the last entry in the file
    if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
        try:
            with open(data_file, "r") as f:
                existing_data_from_file = json.load(f)
                if isinstance(existing_data_from_file, list) and existing_data_from_file:
                    last_entry = existing_data_from_file[-1]
                    # Filter out 'timestamp' and other non-sensor keys and store
                    last_saved_sensor_values.update({
                        'vGrid': last_entry.get('vGrid'),
                        'freqGrid': last_entry.get('freqGrid'),
                        'outPutVolt': last_entry.get('outPutVolt'),
                        'activePower': last_entry.get('activePower'),
                        'capacity': last_entry.get('capacity'),
                        'freqOutPut': last_entry.get('freqOutPut')
                    })
                    log_message(f"Initialized last_saved_sensor_values from file: {last_saved_sensor_values}")
        except json.JSONDecodeError as e:
            log_message(f"⚠️ Could not load last_saved_sensor_values from {data_file} due to JSON error: {e}", level="WARNING")
        except Exception as e:
            log_message(f"⚠️ Could not load last_saved_sensor_values from {data_file}: {e}", level="WARNING")

    while True:
        current_loop_datetime_utc_minus_5 = datetime.now() - timedelta(hours=5)
        current_loop_time_str = current_loop_datetime_utc_minus_5.strftime("%Y-%m-%d %H:%M:%S")

        try:
            # Always attempt to (re)login and get IDs if they are missing
            if user_id is None or plant_id is None or inverter_sn is None or datalog_sn is None:
                log_message("Attempting to acquire Growatt IDs (re-login or initial login).")
                user_id, plant_id, inverter_sn, datalog_sn = login_growatt()
                if user_id is None: # If login/ID fetching fails, wait and try again
                    log_message("Growatt login/ID fetching failed. Retrying in 60 seconds.", level="ERROR")
                    time.sleep(60)
                    continue # Skip to next loop iteration

            # Attempt to fetch storage detail
            raw_growatt_data = api.storage_detail(inverter_sn)
            # log_message(f"Raw Growatt API data received: {raw_growatt_data}") # Too verbose for continuous logging

            # Extract new values for comparison and current_data update
            new_ac_input_v = raw_growatt_data.get("vGrid")
            new_ac_input_f = raw_growatt_data.get("freqGrid")
            new_ac_output_v = raw_growatt_data.get("outPutVolt")
            new_ac_output_f = raw_growatt_data.get("freqOutPut")
            new_load_w = raw_growatt_data.get("activePower")
            new_battery_pct = raw_growatt_data.get("capacity")

            # Store the raw data for console display
            fetched_data.update(raw_growatt_data)

            # Create a dictionary of current sensor values for comparison
            current_sensor_values_for_comparison = {
                "vGrid": new_ac_input_v,
                "freqGrid": new_ac_input_f,
                "outPutVolt": new_ac_output_v,
                "activePower": new_load_w,
                "capacity": new_battery_pct,
                "freqOutPut": new_ac_output_f
            }

            data_to_save_for_file = {}
            growatt_data_is_stale = False

            # Check if the fetched sensor values are IDENTICAL to the last saved ones
            if last_saved_sensor_values and current_sensor_values_for_comparison == last_saved_sensor_values:
                growatt_data_is_stale = True
                log_message("⚠️ Detected Growatt data is identical to last saved values (stale). Saving NULLs for charts.", level="WARNING")

                # If data is stale, prepare data_to_save with None for numerical values
                data_to_save_for_file = {
                    "timestamp": current_loop_time_str,
                    "vGrid": None, # Will become null in JSON
                    "freqGrid": None,
                    "outPutVolt": None,
                    "activePower": None,
                    "capacity": None,
                    "freqOutPut": None,
                }
                # last_successful_growatt_update_time should NOT be updated here.
                # It should reflect when *fresh* data was last received.
            else:
                log_message("✅ New Growatt data received.")
                last_successful_growatt_update_time = current_loop_time_str # Update only on fresh data

                # Prepare data to be saved to file with actual values
                data_to_save_for_file = {
                    "timestamp": last_successful_growatt_update_time, # Use the time when fresh data was received
                    "vGrid": new_ac_input_v,
                    "freqGrid": new_ac_input_f,
                    "outPutVolt": new_ac_output_v,
                    "activePower": new_load_w,
                    "capacity": new_battery_pct,
                    "freqOutPut": new_ac_output_f,
                }

            # Always update `current_data` with the most recently *received* values
            current_data.update({
                "ac_input_voltage": new_ac_input_v,
                "ac_input_frequency": new_ac_input_f,
                "ac_output_voltage": new_ac_output_v,
                "ac_output_frequency": new_ac_output_f,
                "load_power": new_load_w,
                "battery_capacity": new_battery_pct,
                "user_id": user_id,
                "plant_id": plant_id,
                "inverter_sn": inverter_sn,
                "datalog_sn": datalog_sn
            })

            last_processed_time = current_loop_time_str

            # --- Telegram Alerts ---
            if telegram_enabled:
                current_ac_input_v_float = 0.0
                if current_data.get("ac_input_voltage") is not None:
                    try:
                        current_ac_input_v_float = float(current_data.get("ac_input_voltage"))
                    except ValueError:
                        log_message(f"Could not convert AC input voltage '{current_data.get('ac_input_voltage')}' to float for alert comparison.", level="WARNING")

                alert_timestamp = last_successful_growatt_update_time

                # Check if AC input voltage drops below threshold
                if current_ac_input_v_float < threshold and not sent_lights_off:
                    log_message("Potential power outage detected. Confirming in 110 seconds...", level="INFO")
                    time.sleep(110) # Wait a bit to confirm
                    
                    data_confirm = api.storage_detail(inverter_sn)
                    ac_input_v_confirm = data_confirm.get("vGrid")
                    current_ac_input_v_confirm = 0.0
                    if ac_input_v_confirm is not None:
                        try:
                            current_ac_input_v_confirm = float(ac_input_v_confirm)
                        except ValueError:
                            pass # Keep 0.0 if cannot convert

                    if current_ac_input_v_confirm < threshold:
                        msg = f"""🔴🔴¡Se fue la luz en Acacías!🔴🔴
🕒 Hora--> {alert_timestamp}
Nivel de batería      : {current_data.get('battery_capacity', 'N/A')} %
Voltaje de la red     : {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Voltaje del inversor: {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Consumo actual     : {current_data.get('load_power', 'N/A')} W"""
                        send_telegram_message(msg)
                        sent_lights_off = True
                        sent_lights_on = False
                        log_message("Power outage confirmed and alert sent.", level="INFO")
                    else:
                        log_message("Power outage not confirmed after waiting.", level="INFO")

                # Check if AC input voltage returns above threshold
                elif current_ac_input_v_float >= threshold and not sent_lights_on:
                    log_message("Potential power restored detected. Confirming in 110 seconds...", level="INFO")
                    time.sleep(110) # Wait a bit to confirm
                    
                    data_confirm = api.storage_detail(inverter_sn)
                    ac_input_v_confirm = data_confirm.get("vGrid")
                    current_ac_input_v_confirm = 0.0
                    if ac_input_v_confirm is not None:
                        try:
                            current_ac_input_v_confirm = float(ac_input_v_confirm)
                        except ValueError:
                            pass # Keep 0.0 if cannot convert

                    if current_ac_input_v_confirm >= threshold:
                        msg = f"""✅✅¡Llegó la luz en Acacías!✅✅
🕒 Hora--> {alert_timestamp}
Nivel de batería      : {current_data.get('battery_capacity', 'N/A')} %
Voltaje de la red     : {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Voltaje del inversor: {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Consumo actual     : {current_data.get('load_power', 'N/A')} W"""
                        send_telegram_message(msg)
                        sent_lights_on = True
                        sent_lights_off = False
                        log_message("Power restored confirmed and alert sent.", level="INFO")
                    else:
                        log_message("Power restored not confirmed after waiting.", level="INFO")

            # --- Data Saving Frequency Control ---
            # Save data to file only when loop_counter reaches 7 (approx every 4.6 minutes if sleep is 40s)
            loop_counter += 1
            if loop_counter >= 7:
                save_data_to_file(data_to_save_for_file, data_file)
                log_message("✅ Saved data to file (controlled by loop_counter).")
                loop_counter = 0

        except Exception as e_inner:
            log_message(f"❌ Error during Growatt data fetch or processing (API error): {e_inner}", level="ERROR")
            # If there's an API error, we do NOT update last_successful_growatt_update_time.
            # We also do NOT save a data point for this cycle to the file.
            # Reset IDs to force re-login attempt in next loop
            user_id, plant_id, inverter_sn, datalog_sn = None, None, None, None

        finally:
            time.sleep(40) # Wait for 40 seconds before next API call

# --- Telegram Handlers ---
def start(update: Update, context: CallbackContext):
    """Handles the /start command from Telegram."""
    chat_log.add(update.effective_chat.id)
    update.message.reply_text("¡Bienvenido al monitor Growatt! Usa /status para ver el estado del inversor.")
    log_message(f"Telegram /start command received from {update.effective_chat.id}")

def send_status(update: Update, context: CallbackContext):
    """Handles the /status command from Telegram."""
    chat_log.add(update.effective_chat.id)
    timestamp = (datetime.now() - timedelta(hours=5)).strftime("%H:%M:%S")

    msg = f"""⚡ /status Estado del Inversor /stop⚡
🕒 Hora--> {timestamp}
Voltaje Red          : {current_data.get('ac_input_voltage', 'N/A')} V / {current_data.get('ac_input_frequency', 'N/A')} Hz
Voltaje Inversor   : {current_data.get('ac_output_voltage', 'N/A')} V / {current_data.get('ac_output_frequency', 'N/A')} Hz
Consumo             : {current_data.get('load_power', 'N/A')} W
Batería                 : {current_data.get('battery_capacity', 'N/A')}%
"""
    try:
        update.message.reply_text(msg)
        log_message(f"✅ Status sent to {update.effective_chat.id}")
    except Exception as e:
        log_message(f"❌ Failed to send status to {update.effective_chat.id}: {e}", level="ERROR")

def send_chatlog(update: Update, context: CallbackContext):
    """Handles the /chatlog command from Telegram."""
    chat_log.add(update.effective_chat.id)
    ids = "\n".join(str(cid) for cid in chat_log)
    update.message.reply_text(f"IDs registrados:\n{ids}")
    log_message(f"Telegram /chatlog command received from {update.effective_chat.id}")

def stop_bot_telegram_command(update: Update, context: CallbackContext):
    """Handles the /stop command from Telegram, stopping the bot."""
    update.message.reply_text("Bot detenido.")
    log_message("Bot detenido por comando /stop")
    global telegram_enabled, updater
    if updater and updater.running:
        updater.stop()
        telegram_enabled = False
        log_message("Telegram bot stopped via /stop command.")
    else:
        log_message("Telegram bot not running to be stopped.", level="WARNING")

def initialize_telegram_bot():
    """Initializes and starts the Telegram bot polling."""
    global updater, dp, TELEGRAM_TOKEN, telegram_enabled
    if not TELEGRAM_TOKEN:
        log_message("❌ Cannot start Telegram bot: TELEGRAM_TOKEN is empty.", level="ERROR")
        return False

    if updater and updater.running:
        log_message("Telegram bot is already running. No re-initialization needed unless token changed.")
        return True

    try:
        log_message("Initializing Telegram bot...")
        updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
        dp = updater.dispatcher
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("status", send_status))
        dp.add_handler(CommandHandler("chatlog", send_chatlog))
        dp.add_handler(CommandHandler("stop", stop_bot_telegram_command))
        updater.start_polling()
        log_message("Telegram bot polling started.")
        telegram_enabled = True
        return True
    except Exception as e:
        log_message(f"❌ Error starting Telegram bot (check token): {e}", level="ERROR")
        updater = None
        dp = None
        telegram_enabled = False
        return False

# --- Flask Routes ---
@app.route("/")
def home():
    """Renders the home page with current data and Telegram status."""
    global TELEGRAM_TOKEN, last_successful_growatt_update_time
    displayed_token = TELEGRAM_TOKEN
    if TELEGRAM_TOKEN and len(TELEGRAM_TOKEN) > 10:
        displayed_token = TELEGRAM_TOKEN[:5] + "..." + TELEGRAM_TOKEN[-5:]

    return render_template("home.html",
        d=current_data,
        last_growatt_update=last_successful_growatt_update_time,
        plant_id=current_data.get("plant_id", "N/A"),
        user_id=current_data.get("user_id", "N/A"),
        inverter_sn=current_data.get("inverter_sn", "N/A"),
        datalog_sn=current_data.get("datalog_sn", "N/A"),
        telegram_status="Running" if telegram_enabled and updater and updater.running else "Stopped",
        current_telegram_token=displayed_token
        )

@app.route("/toggle_telegram", methods=["POST"])
def toggle_telegram():
    """Toggles the Telegram bot on or off."""
    global telegram_enabled, updater
    action = request.form.get('action')

    if action == 'start' and not telegram_enabled:
        log_message("Attempting to start Telegram bot via Flask.")
        if initialize_telegram_bot():
            log_message("Telegram bot enabled.")
        else:
            log_message("Failed to enable Telegram bot (check logs for token error).", level="ERROR")
    elif action == 'stop' and telegram_enabled:
        log_message("Attempting to stop Telegram bot via Flask.")
        if updater and updater.running:
            updater.stop()
            telegram_enabled = False
            log_message("Telegram bot stopped.")
        else:
            log_message("Telegram bot not running to be stopped.", level="WARNING")

    return redirect(url_for('home'))

@app.route("/update_telegram_token", methods=["POST"])
def update_telegram_token():
    """Updates the Telegram bot token and restarts the bot."""
    global TELEGRAM_TOKEN, telegram_enabled, updater, dp
    new_token = request.form.get('new_telegram_token')

    if not new_token:
        log_message("❌ No new Telegram token provided.", level="WARNING")
        return redirect(url_for('home'))

    log_message(f"Attempting to update Telegram token...")

    if updater and updater.running:
        log_message("Stopping existing Telegram bot for token update.")
        try:
            updater.stop()
            time.sleep(1) # Give it a moment to shut down
            log_message("Existing Telegram bot stopped.")
        except Exception as e:
            log_message(f"⚠️ Error stopping existing Telegram bot: {e}", level="WARNING")
        finally:
            updater = None # Clear references
            dp = None

    TELEGRAM_TOKEN = new_token
    log_message(f"Telegram token updated to: {new_token[:5]}...{new_token[-5:]}")

    if initialize_telegram_bot():
        log_message("Telegram bot restarted successfully with new token.")
    else:
        log_message("❌ Failed to restart Telegram bot with new token. It remains disabled. Check logs for details.", level="ERROR")

    return redirect(url_for('home'))

@app.route("/logs")
def charts_view():
    """Renders the charts page with historical data."""
    global last_successful_growatt_update_time
    parsed_data = []
    if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
        try:
            with open(data_file, "r") as file:
                parsed_data = json.load(file)
            if not isinstance(parsed_data, list):
                log_message(f"❌ Data file {data_file} does not contain a JSON list. Resetting.", level="ERROR")
                parsed_data = []
        except json.JSONDecodeError as e:
            log_message(f"❌ Error decoding JSON from {data_file}: {e}. File might be corrupted. Resetting data.", level="ERROR")
            parsed_data = []
        except Exception as e:
            log_message(f"❌ General error reading data for charts from {data_file}: {e}", level="ERROR")
            parsed_data = []
    else:
        log_message(f"⚠️ Data file not found or empty: {data_file}. Charts will be empty.", level="WARNING")
        # Ensure the file exists and is initialized if it's not.
        try:
            with open(data_file, "w") as f:
                f.write("[]")
            log_message(f"Initialized empty data file: {data_file}")
        except Exception as e:
            log_message(f"❌ Error initializing empty data file: {e}", level="ERROR")

    processed_data = []
    for entry in parsed_data:
        if 'timestamp' in entry and isinstance(entry['timestamp'], str):
            try:
                entry['dt_timestamp'] = datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S")
                processed_data.append(entry)
            except ValueError:
                log_message(f"Skipping entry with invalid timestamp format: {entry.get('timestamp')}", level="WARNING")
        else:
            log_message(f"Skipping entry with missing or non-string timestamp: {entry}", level="WARNING")

    processed_data.sort(key=lambda x: x['dt_timestamp'])

    max_duration_hours_to_send = 96 # Display last 96 hours (4 days)

    if processed_data:
        reference_time = processed_data[-1]['dt_timestamp']
    else:
        reference_time = datetime.now()

    cutoff_time = reference_time - timedelta(hours=max_duration_hours_to_send)

    filtered_data_for_frontend = [
        entry for entry in processed_data
        if entry['dt_timestamp'] >= cutoff_time
    ]

    timestamps = [entry['timestamp'] for entry in filtered_data_for_frontend]
    # Handle None values for chart data by explicitly converting to float/int for numbers,
    # but allowing None to pass through for chart compatibility.
    ac_input = [float(entry['vGrid']) if entry.get('vGrid') is not None else None for entry in filtered_data_for_frontend]
    ac_output = [float(entry['outPutVolt']) if entry.get('outPutVolt') is not None else None for entry in filtered_data_for_frontend]
    active_power = [int(entry['activePower']) if entry.get('activePower') is not None else None for entry in filtered_data_for_frontend]
    battery_capacity = [int(entry['capacity']) if entry.get('capacity') is not None else None for entry in filtered_data_for_frontend]

    return render_template("logs.html",
        timestamps=timestamps,
        ac_input=ac_input,
        ac_output=ac_output,
        active_power=active_power,
        battery_capacity=battery_capacity,
        last_growatt_update=last_successful_growatt_update_time)

@app.route("/chatlog")
def chatlog_view():
    """Renders a simple page to display current chat IDs."""
    return render_template_string("""
        <html>
        <head>
            <title>Growatt Monitor - Chatlog</title>
            <meta name="viewport" content="width=device-width, initial-scale=0.6, maximum-scale=1.0, user-scalable=yes">
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                }
                nav {
                    background-color: #333;
                    overflow: hidden;
                    position: sticky;
                    top: 0;
                    z-index: 100;
                }
                nav ul {
                    list-style-type: none;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                }
                nav ul li {
                    padding: 14px 20px;
                }
                nav ul li a {
                    color: white;
                    text-decoration: none;
                    font-size: 18px;
                }
                nav ul li a:hover {
                    background-color: #ddd;
                    color: black;
                }
            </style>
        </head>
        <body>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/logs">Logs</a></li>
                    <li><a href="/chatlog">Chatlog</a></li>
                    <li><a href="/console">Console</a></li>
                    <li><a href="/details">Details</a></li>
                    <li><a href="/battery-chart">Battery Chart</a></li>
                </ul>
            </nav>
            <h1>Chatlog</h1>
            <pre>{{ chat_log }}</pre>
        </body>
        </html>
    """, chat_log="\n".join(str(cid) for cid in sorted(list(chat_log))))

@app.route("/console")
def console_view():
    """Renders a page to display console logs and fetched Growatt data."""
    # Filter logs to only show messages from the last 5 minutes (300 seconds) for this view
    current_time = time.time()
    recent_logs = [m for t, m in console_logs if current_time - t < 300]

    return render_template_string("""
        <html>
        <head>
            <title>Console Logs</title>
            <meta name="viewport" content="width=device-width, initial-scale=0.6, maximum-scale=1.0, user-scalable=yes">
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                }
                nav {
                    background-color: #333;
                    overflow: hidden;
                    position: sticky;
                    top: 0;
                    z-index: 100;
                }
                nav ul {
                    list-style-type: none;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                }
                nav ul li {
                    padding: 14px 20px;
                }
                nav ul li a {
                    color: white;
                    text-decoration: none;
                    font-size: 18px;
                }
                nav ul li a:hover {
                    background-color: #ddd;
                    color: black;
                }
            </style>
        </head>
        <body>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/logs">Logs</a></li>
                    <li><a href="/chatlog">Chatlog</a></li>
                    <li><a href="/console">Console</a></li>
                    <li><a href="/details">Details</a></li>
                    <li><a href="/battery-chart">Battery Chart</a></li>
                </ul>
            </nav>
            <h2>Console Output (últimos 5 minutos)</h2>
            <pre style="white-space: pre-wrap; word-wrap: break-word; font-family: monospace; overflow-x: auto; background-color: #f0f0f0; padding: 10px; border-radius: 5px;">{{ logs }}</pre>

            <h2>📦 Fetched Growatt Data (Last API Response)</h2>
            <pre style="white-space: pre-wrap; word-wrap: break-word; font-family: monospace; overflow-x: auto; background-color: #f0f0f0; padding: 10px; border-radius: 5px;">{{ data }}</pre>
        </body>
        </html>
    """,
    logs="\n".join(recent_logs),
    data=pprint.pformat(fetched_data, indent=2)) # Using pprint for better formatting of dict

@app.route("/details")
def details_view():
    """Renders a page with detailed current data (similar to Home but potentially more raw)."""
    return render_template_string("""
        <html>
        <head>
            <title>Growatt Monitor - Details</title>
            <meta name="viewport" content="width=device-width, initial-scale=0.6, maximum-scale=1.0, user-scalable=yes">
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                }
                nav {
                    background-color: #333;
                    overflow: hidden;
                    position: sticky;
                    top: 0;
                    z-index: 100;
                }
                nav ul {
                    list-style-type: none;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                }
                nav ul li {
                    padding: 14px 20px;
                }
                nav ul li a {
                    color: white;
                    text-decoration: none;
                    font-size: 18px;
                }
                nav ul li a:hover {
                    background-color: #ddd;
                    color: black;
                }
                .container {
                    padding: 20px;
                }
                .data-item {
                    margin-bottom: 10px;
                }
                .data-item strong {
                    display: inline-block;
                    width: 200px;
                }
            </style>
        </head>
        <body>
            <nav>
                <ul>
                    <li><a href="/">Home</a></li>
                    <li><a href="/logs">Logs</a></li>
                    <li><a href="/chatlog">Chatlog</a></li>
                    <li><a href="/console">Console</a></li>
                    <li><a href="/details">Details</a></li>
                    <li><a href="/battery-chart">Battery Chart</a></li>
                </ul>
            </nav>
            <div class="container">
                <h1>Current Growatt Data Details</h1>
                <div class="data-item"><strong>Last Processed Time:</strong> {{ last_processed_time }}</div>
                <div class="data-item"><strong>Last Fresh Data Time:</strong> {{ last_growatt_update }}</div>
                <div class="data-item"><strong>AC Input Voltage:</strong> {{ d.get('ac_input_voltage', 'N/A') }} V</div>
                <div class="data-item"><strong>AC Input Frequency:</strong> {{ d.get('ac_input_frequency', 'N/A') }} Hz</div>
                <div class="data-item"><strong>AC Output Voltage:</strong> {{ d.get('ac_output_voltage', 'N/A') }} V</div>
                <div class="data-item"><strong>AC Output Frequency:</strong> {{ d.get('ac_output_frequency', 'N/A') }} Hz</div>
                <div class="data-item"><strong>Load Power:</strong> {{ d.get('load_power', 'N/A') }} W</div>
                <div class="data-item"><strong>Battery Capacity:</strong> {{ d.get('battery_capacity', 'N/A') }}%</div>
                <div class="data-item"><strong>User ID:</strong> {{ d.get('user_id', 'N/A') }}</div>
                <div class="data-item"><strong>Plant ID:</strong> {{ d.get('plant_id', 'N/A') }}</div>
                <div class="data-item"><strong>Inverter SN:</strong> {{ d.get('inverter_sn', 'N/A') }}</div>
                <div class="data-item"><strong>Datalogger SN:</strong> {{ d.get('datalog_sn', 'N/A') }}</div>
                <hr>
                <h2>Raw `current_data` Dictionary:</h2>
                <pre style="white-space: pre-wrap; word-wrap: break-word; font-family: monospace; background-color: #f0f0f0; padding: 10px; border-radius: 5px;">{{ d | tojson(indent=2) }}</pre>
            </div>
        </body>
        </html>
    """,
    d=current_data,
    last_processed_time=last_processed_time,
    last_growatt_update=last_successful_growatt_update_time)

@app.route("/battery-chart", methods=["GET", "POST"])
def battery_chart():
    """Renders the battery and energy charts for a selected date."""
    global last_successful_growatt_update_time
    selected_date = request.form.get("date") or get_today_date_utc_minus_5()

    growatt_login2() # Ensure session is logged in

    battery_payload = {
        'plantId': PLANT_ID,
        'storageSn': STORAGE_SN,
        'date': selected_date
    }

    battery_data = {}
    try:
        battery_response = session.post(
            'https://server.growatt.com/panel/storage/getStorageBatChart',
            headers=HEADERS,
            data=battery_payload,
            timeout=10
        )
        battery_response.raise_for_status()
        battery_data = battery_response.json()
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Failed to fetch battery data for {selected_date}: {e}", level="ERROR")

    soc_data = battery_data.get("obj", {}).get("socChart", {}).get("capacity", [])
    if not soc_data:
        log_message(f"⚠️ No SoC data received for {selected_date}", level="WARNING")
    # Pad to 288 points if data is shorter (24 hours * 12 points/hour = 288)
    soc_data = soc_data + [None] * (288 - len(soc_data))

    energy_payload = {
        "date": selected_date,
        "plantId": PLANT_ID,
        "storageSn": STORAGE_SN
    }

    energy_data = {}
    try:
        energy_response = session.post(
            "https://server.growatt.com/panel/storage/getStorageEnergyDayChart",
            headers=HEADERS,
            data=energy_payload,
            timeout=10
        )
        energy_response.raise_for_status()
        energy_data = energy_response.json()
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Failed to fetch energy chart data for {selected_date}: {e}", level="ERROR")

    energy_obj = energy_data.get("obj", {}).get("charts", {})
    energy_titles = energy_data.get("titles", [])

    def prepare_series(data_list, name, color):
        """Helper to format data for Highcharts series."""
        cleaned_data = []
        for x in data_list:
            if isinstance(x, (int, float)):
                cleaned_data.append(float(x))
            elif isinstance(x, str) and x.replace('.', '', 1).isdigit():
                cleaned_data.append(float(x))
            else:
                cleaned_data.append(None) # Convert 'N/A' or other non-numeric to None

        if not cleaned_data or all(x is None for x in cleaned_data):
            return None # Return None if no valid data points
        return {"name": name, "data": cleaned_data, "color": color, "fillOpacity": 0.2, "lineWidth": 1}

    energy_series = [
        prepare_series(energy_obj.get("ppv"), "Photovoltaic Output", "#FFEB3B"),
        prepare_series(energy_obj.get("userLoad"), "Load Consumption", "#9C27B0"),
        prepare_series(energy_obj.get("pacToUser"), "Imported from Grid", "#00BCD4"),
        # Add other relevant series if desired, e.g., "pacToGrid" for exported to grid
    ]
    # Filter out any series that are None (i.e., had no valid data)
    energy_series = [s for s in energy_series if s]

    if not any(series and series['data'] for series in energy_series):
        log_message(f"⚠️ No usable energy chart data received for {selected_date}", level="WARNING")

    # Ensure all series have 288 data points, padding with None if necessary
    for series in energy_series:
        if series and series["data"]:
            series["data"] = series["data"] + [None] * (288 - len(series["data"]))
        elif series: # If series exists but data was empty, create empty data array
            series["data"] = [None] * 288

    return render_template(
        "battery-chart.html",
        selected_date=selected_date,
        soc_data=soc_data,
        raw_json=json.dumps(battery_data, indent=2), # Pass raw JSON for inspection
        energy_titles=energy_titles,
        energy_series=energy_series,
        last_growatt_update=last_successful_growatt_update_time
    )

@app.route('/dn')
def download_logs():
    """Allows downloading the main data file."""
    try:
        return send_file(data_file, as_attachment=True, download_name="saved_data.json", mimetype="application/json")
    except FileNotFoundError:
        log_message(f"❌ Download failed: {data_file} not found.", level="ERROR")
        return "File not found.", 404
    except Exception as e:
        log_message(f"❌ Error downloading file: {e}", level="ERROR")
        return f"Error downloading file: {e}", 500

@app.route("/trigger_github_sync", methods=["POST"])
def trigger_github_sync():
    """Manually triggers a GitHub sync specifically for the TEST data file."""
    log_message("Received request to manually trigger GitHub sync for TEST file.")
    # Start the sync operation in a new daemon thread
    sync_thread = threading.Thread(target=_perform_single_github_sync_operation, daemon=True)
    sync_thread.start()
    return redirect(url_for('charts_view'))

# --- Initial File Setup ---
# Ensure the main data file exists and is initialized as an empty JSON array
if not os.path.exists(data_file) or os.path.getsize(data_file) == 0:
    try:
        os.makedirs(os.path.dirname(data_file) or '.', exist_ok=True) # Ensure directory exists
        with open(data_file, "w") as f:
            f.write("[]")
        log_message(f"Initialized empty data file: {data_file}")
    except Exception as e:
        log_message(f"❌ Error initializing main data file {data_file}: {e}", level="FATAL")

# Ensure the test data file exists and is initialized as an empty JSON array
if not os.path.exists(TEST_DATA_FILE) or os.path.getsize(TEST_DATA_FILE) == 0:
    try:
        os.makedirs(os.path.dirname(TEST_DATA_FILE) or '.', exist_ok=True) # Ensure directory exists
        with open(TEST_DATA_FILE, "w") as f:
            f.write("[]")
        log_message(f"Initialized empty test data file: {TEST_DATA_FILE}")
    except Exception as e:
        log_message(f"❌ Error initializing test data file {TEST_DATA_FILE}: {e}", level="FATAL")


# --- Main Execution Block ---
if __name__ == '__main__':
    # Start the Growatt monitoring thread
    monitor_thread = threading.Thread(target=monitor_growatt, daemon=True)
    monitor_thread.start()
    log_message("Growatt monitor thread started.")

    # Start the GitHub sync thread
    github_sync_thread = threading.Thread(target=sync_github_repo, daemon=True)
    github_sync_thread.start()
    log_message("GitHub sync thread started.")

    # Start the Flask app
    log_message(f"Starting Flask app on http://{HOST_IP}:{PORT}")
    app.run(debug=DEBUG_MODE, host=HOST_IP, port=PORT, use_reloader=False) # use_reloader=False when using threads

    log_message("Flask app terminated.")

import os
import json
import git
from datetime import datetime

# Configuration
GITHUB_REPO_URL = "github.com/sjimenezn/growatt2.git"
GITHUB_USERNAME = "sjimenezn"  # Fixed typo from previous version
GITHUB_TOKEN = os.getenv("GITHUB_PAT")
LOCAL_REPO_PATH = "."
TEST_FILE_NAME = "saved_data_test.json"

def force_push_to_github():
    """Ensures branch alignment and force-pushes to GitHub"""
    try:
        # Initialize repo (clone if not exists)
        repo_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@{GITHUB_REPO_URL}"
        
        if not os.path.exists(os.path.join(LOCAL_REPO_PATH, '.git')):
            print("🔄 Cloning fresh repository...")
            repo = git.Repo.clone_from(repo_url, LOCAL_REPO_PATH, branch="main")
        else:
            repo = git.Repo(LOCAL_REPO_PATH)
            print("✅ Using existing repository")

        # Fetch all remote branches
        print("🔄 Fetching remote branches...")
        repo.remotes.origin.fetch()

        # Check if main branch exists locally
        if 'main' not in repo.heads:
            print("🔄 Creating local main branch tracking origin/main")
            repo.git.checkout('-b', 'main', 'origin/main')

        # Fix detached HEAD state
        if repo.head.is_detached:
            print("⚠️ Fixing detached HEAD state...")
            repo.git.checkout('main')  # Just checkout main, don't reset yet

        # Ensure we're on main branch
        if repo.active_branch.name != "main":
            print("🔄 Switching to main branch...")
            repo.git.checkout('main')

        # Reset to origin/main (now that we know it exists)
        print("🔄 Resetting to origin/main...")
        repo.git.reset('--hard', 'origin/main')

        # Create test file
        test_data = {
            "timestamp": datetime.now().isoformat(),
            "status": "TESTING",
            "message": "Successful push test"
        }
        with open(TEST_FILE_NAME, 'w') as f:
            json.dump(test_data, f, indent=2)

        # Stage, commit and push
        print("🚀 Pushing changes...")
        repo.git.add('--all')
        repo.git.commit('-m', f'Test update {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', '--no-verify')
        repo.git.push('origin', 'main', force=True)

        print("✅ Successfully pushed to GitHub!")
        return True

    except Exception as e:
        print(f"❌ Failed to push: {str(e)}")
        return False

if __name__ == "__main__":
    if not GITHUB_TOKEN:
        print("❌ ERROR: GITHUB_PAT environment variable not set!")
    else:
        force_push_to_github()
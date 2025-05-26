import os
import json
import git
from datetime import datetime

# Configuration
GITHUB_REPO_URL = "github.com/sjimenezn/growatt2.git"
GITHUB_USERNAME = "sjimenezn"
GITHUB_TOKEN = os.getenv("GITHUB_PAT")  # Make sure this is set in your environment
LOCAL_REPO_PATH = "."  # Current directory
TEST_FILE_NAME = "saved_data_test.json"

def initialize_repository():
    """Initialize or clone the Git repository"""
    repo = None
    repo_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@{GITHUB_REPO_URL}"
    
    try:
        # Check if repository already exists
        if os.path.exists(os.path.join(LOCAL_REPO_PATH, '.git')):
            repo = git.Repo(LOCAL_REPO_PATH)
            print("✅ Using existing repository")
        else:
            print("🔄 Cloning repository...")
            repo = git.Repo.clone_from(repo_url, LOCAL_REPO_PATH)
            print("✅ Repository cloned successfully")
        
        # Configure git identity (required for commits)
        with repo.config_writer() as git_config:
            git_config.set_value("user", "name", "Koyeb Deployment")
            git_config.set_value("user", "email", "deploy@koyeb.com")
        
        return repo
        
    except Exception as e:
        print(f"❌ Failed to initialize repository: {str(e)}")
        return None

def create_test_file():
    """Create the test file with current timestamp"""
    test_content = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "TESTING",
        "message": "This is a test file for GitHub upload"
    }
    
    try:
        with open(TEST_FILE_NAME, 'w') as f:
            json.dump(test_content, f, indent=2)
        print(f"✅ Created {TEST_FILE_NAME}")
        return True
    except Exception as e:
        print(f"❌ Failed to create test file: {str(e)}")
        return False

def push_to_github(repo):
    """Stage, commit, and push changes to GitHub"""
    try:
        # Stage the file
        repo.index.add([TEST_FILE_NAME])
        print("✅ Staged changes")
        
        # Commit
        commit_message = f"Add test file {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        repo.index.commit(commit_message)
        print(f"✅ Committed: {commit_message}")
        
        # Push to origin/main
        origin = repo.remote(name='origin')
        origin.push(refspec='main:main')
        print("✅ Pushed to GitHub")
        return True
        
    except Exception as e:
        print(f"❌ Failed to push to GitHub: {str(e)}")
        return False

def main():
    print("🚀 Starting GitHub upload test")
    
    # Verify GitHub token is available
    if not GITHUB_TOKEN:
        print("❌ GITHUB_PAT environment variable not set")
        return
    
    # Initialize repository
    repo = initialize_repository()
    if not repo:
        return
    
    # Create test file
    if not create_test_file():
        return
    
    # Push to GitHub
    if not push_to_github(repo):
        return
    
    print("🎉 Successfully uploaded test file to GitHub")

if __name__ == "__main__":
    main()

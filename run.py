import uvicorn
import os
import sys

if __name__ == "__main__":
    # Ensure working directory is set to the project root
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    sys.path.insert(0, project_root)
    
    # Start the server on port 5678
    uvicorn.run("app.main:app", host="127.0.0.1", port=5678, reload=True)

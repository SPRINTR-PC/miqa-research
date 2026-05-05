from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.absolute()))

from build_dotnet_release import build_dotnet_projects, list_dotnet_projects

DOTNET_PROJECT_LIST_EXCLUDE_LIST = ("Miqa.Core", "Miqa.Infrastructure")
MAIN_DOTNET_DIR = Path(__file__).parent.parent.parent / "src/dotnet"
MAIN_MIQA_RESEARCH_DIR = Path(__file__).parent.parent.parent / "src/MiqaResearch"



def main():
    dotnet_projects = list_dotnet_projects(MAIN_DOTNET_DIR, DOTNET_PROJECT_LIST_EXCLUDE_LIST)
    build_dotnet_projects(MAIN_DOTNET_DIR, dotnet_projects)
    pass

if __name__ == "__main__":
    main()

import concurrent.futures
from pathlib import Path


def list_dotnet_projects(main_dotnet_dir: Path, exclude_dir_list: tuple[str, ...]) -> list[str]:
    return [
        directory.name
        for directory in main_dotnet_dir.iterdir()
        if directory.is_dir() and directory.name not in exclude_dir_list
    ]


def build_dotnet_projects(main_dotnet_dir: Path, project_name_list: list[str]):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(build_dotnet_project_release, main_dotnet_dir, project_name)
            for project_name in project_name_list
        ]
        concurrent.futures.wait(futures)


def build_dotnet_project_release(main_dotnet_dir: Path, project_name: str):
    pass
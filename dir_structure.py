import os
import json


def list_files(startpath):
    tree = {}
    for root, dirs, files in os.walk(startpath):
        # Skip everything inside 'clientportal.gw'
        if "clientportal.gw" in root or ".git" in root:
            continue
        # Getting relative path from startpath
        relative_root = os.path.relpath(root, startpath)
        subtree = tree
        # If not in root, then build the substructure
        if relative_root != ".":
            path_elements = relative_root.split(os.path.sep)
            for elem in path_elements:
                subtree = subtree.setdefault(elem, {})
        # Add files to the current subtree
        for file_name in files:
            subtree[
                file_name
            ] = None  # None indicates this is a file and not a sub-directory
    return tree


# Start from current directory
tree_structure = list_files(os.getcwd())

with open("directory_structure.json", "w") as f:
    json.dump(tree_structure, f, indent=4)

print("Directory structure saved to 'directory_structure.json'")

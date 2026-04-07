import os

files_to_fix = [
    '/home/ella/.bashrc',
    '/home/ella/.profile',
    '/home/ella/.bash_profile'
]

for file_path in files_to_fix:
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            content = f.read()

        new_content = content.replace('/var/home/david', '/home/ella')
        new_content = new_content.replace('/home/david', '/home/ella')

        if new_content != content:
            with open(file_path, 'w') as f:
                f.write(new_content)
            print(f"Fixed paths in {file_path}")
print("Finished fixing bash profile files.")

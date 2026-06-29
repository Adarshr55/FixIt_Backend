import importlib.metadata

for dist in importlib.metadata.distributions():
    try:
        top = dist._path / 'top_level.txt'
        if top.exists():
            top.read_text(encoding='utf-8')
    except Exception as e:
        print(f'BAD: {dist.metadata["Name"]} -> {e}')

print("scan complete")
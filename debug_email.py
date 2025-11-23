import os

env_path = os.path.join("maf_agent", ".env")

print(f"Checking file at: {os.path.abspath(env_path)}")

if not os.path.exists(env_path):
    print("❌ FILE DOES NOT EXIST!")
else:
    print("✅ File exists.")
    print("-" * 20)
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
            print(f"File Content Length: {len(content)} chars")
            print("First 50 chars raw repr:", repr(content[:50]))
            
            # Manual parsing attempt
            for line in content.splitlines():
                if line.startswith("EMAIL_ACCOUNT"):
                    print(f"FOUND LINE: {line}")
    except Exception as e:
        print(f"❌ Error reading file: {e}")

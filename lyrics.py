import time
import sys

RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"
GREEN   = "\033[92m"
BLUE    = "\033[94m"
PURPLE  = "\033[95m"
WHITE   = "\033[97m"
MAGENTA = "\033[95m"

def print_lyrics():

    lyrics = [
        ("ʜᴜᴍ ᴘʏᴀʀ ᴋᴀʀɴᴇ ᴡᴀʟᴇ ❤️", CYAN),
        ("ᴅᴜɴɪʏᴀ ꜱᴇ ɴᴀ ᴅᴀʀɴᴇ ᴡᴀʟᴇ..", YELLOW),
        ("ᴅᴜɴɪʏᴀ ꜱᴇ ɴᴀ ᴅᴀʀɴᴇ ᴡᴀʟᴇ..", PURPLE),
        ("ᴘʏᴀʀ ᴋᴀʀɴᴇ ᴡᴀʟᴏɴ ᴋᴏ ᴊᴀʟᴀʏᴇɴɢᴇ", RED),
        ("ᴘʏᴀʀ ᴍᴀɪ ᴊɪʏᴇɴɢᴇ ᴍᴀʀ ᴊᴀʏᴇɴɢᴇ ❤️", GREEN),
        ("ᴘʏᴀʀ ᴋᴀʀɴᴇ ᴡᴀʟᴏɴ ᴋᴏ ᴊᴀʟᴀʏᴇɴɢᴇ", RED),
        ("ᴘʏᴀʀ ᴍᴀɪ ᴊɪʏᴇɴɢᴇ ᴍᴀʀ ᴊᴀʏᴇɴɢᴇ ❤️", GREEN),
    ]

    print(f"\n{BOLD}🎵 ᴍᴜꜱɪᴄ ᴘʟᴀʏɪɴɢ 🎵{RESET}\n")
    time.sleep(1)

    for line, color in lyrics:
        for ch in line:
            sys.stdout.write(f"{color}{BOLD}{ch}{RESET}")
            sys.stdout.flush()
            time.sleep(0.06)
        print()
        time.sleep(0.5)

print_lyrics()

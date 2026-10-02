import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")
ADMIN_GID = os.getenv("ADMIN_GID")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cop.db")

# RP Constants (External - Event)
RP_EXT_EV_PARTICIPANT = int(os.getenv("RP_EXT_EV_PARTICIPANT", 25))
RP_EXT_EV_3RD = int(os.getenv("RP_EXT_EV_3RD", 35))
RP_EXT_EV_2ND = int(os.getenv("RP_EXT_EV_2ND", 45))
RP_EXT_EV_1ST = int(os.getenv("RP_EXT_EV_1ST", 55))

# RP Constants (External - Competition)
RP_EXT_COMP_PARTICIPANT = int(os.getenv("RP_EXT_COMP_PARTICIPANT", 50))
RP_EXT_COMP_3RD = int(os.getenv("RP_EXT_COMP_3RD", 100))
RP_EXT_COMP_2ND = int(os.getenv("RP_EXT_COMP_2ND", 150))
RP_EXT_COMP_1ST = int(os.getenv("RP_EXT_COMP_1ST", 200))

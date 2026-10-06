import dbus
from app_config import load_config

# The wallpaper comes from ~/.config/can-you-break-the-bank/can-you-break-the-bank.cfg
config = load_config()

def set_wallpaper(image_path):
    # Create a session D-Bus interface to the plasmashell
    bus = dbus.SessionBus()
    plasma = bus.get_object("org.kde.plasmashell", "/PlasmaShell")
    interface = dbus.Interface(plasma, dbus_interface="org.kde.PlasmaShell")

    # Send the D-Bus command to change the wallpaper
    script = f"""
    var Desktops = desktops();
    for (i = 0; i < Desktops.length; i++) {{
        d = Desktops[i];
        d.wallpaperPlugin = "org.kde.image";
        d.currentConfigGroup = Array("Wallpaper", "org.kde.image", "General");
        d.writeConfig("Image", "file://{image_path}");
    }}
    """
    interface.evaluateScript(script)
    print(f"Wallpaper set to {image_path}")

# Example usage
set_wallpaper(config["enrol_wallpaper"])

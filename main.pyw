import customtkinter as ctk
import requests
import threading
import time
import os
import webbrowser
import urllib.parse
import subprocess
from dotenv import load_dotenv
from haversine import haversine
from tkinter import messagebox
from PIL import Image
from dataclasses import dataclass, field
from typing import Optional, Tuple
import pystray

import geoapify_api # Import the refactored API module

# SETUP
load_dotenv()
EMERGENCY_PHONES_STR = os.getenv("EMERGENCY_NUMBERS", "918153038559")
EMERGENCY_PHONES = [phone.strip() for phone in EMERGENCY_PHONES_STR.split(',')]
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# CONSTANTS
LOCATION_POLL_INTERVAL_SEC = 10
DISCOVERY_COOLDOWN_SEC = 120
DISCOVERY_RADIUS_KM = 0.5 # in kilometers
UKA_TARSADIA_COORDS = (21.069, 73.1332)
UKA_TARSADIA_NAME = "Uka Tarsadia University"

@dataclass
class AppState:
    """A centralized dataclass to hold the application's state."""
    last_coords: Optional[Tuple[float, float]] = None
    last_discovery_time: float = 0.0
    sos_coords: Optional[Tuple[float, float]] = None
    sos_location_name: str = "your current location"

class SpotterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Spotter Pro")
        self.geometry("600x550")
        
        # 1. LOGO CONFIGURATION
        try:
            self.iconbitmap("logo.ico") # Title bar icon
        except Exception:
            pass 

        self.protocol('WM_DELETE_WINDOW', self.minimize_to_tray)
        
        self.app_state = AppState()
        self.stop_event = threading.Event()
        
        # UI ELEMENTS
        self.label_status = ctk.CTkLabel(self, text="SENSING ACTIVE", text_color="#00FF7F", font=("Segoe UI", 26, "bold"))
        self.label_status.pack(pady=(30, 5))

        self.coords_display = ctk.CTkLabel(self, text="Waiting for GPS lock...", font=("Consolas", 14))
        self.coords_display.pack(pady=5)

        self.textbox = ctk.CTkTextbox(self, width=540, height=280, font=("Segoe UI", 12), corner_radius=15)
        self.textbox.pack(pady=20)
        self.log_to_ui("Spotter Engine Initialized. Monitoring location...")

        self.check_emergency_numbers_config()

        self.btn_refresh = ctk.CTkButton(self, text="[SCAN] RE-SCAN ALL ESSENTIALS", command=self.manual_check, 
                                          fg_color="#1f538d", hover_color="#14375e", height=45, font=("Segoe UI", 14, "bold"))
        self.btn_refresh.pack(pady=10)

        self.sos_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.sos_frame.pack(pady=10, padx=20, fill="x")

        ctk.CTkLabel(self.sos_frame, text="SOS Location:", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        self.location_button_frame = ctk.CTkFrame(self.sos_frame, fg_color="transparent")
        self.location_button_frame.pack(fill="x")

        self.btn_set_custom_loc = ctk.CTkButton(
            self.location_button_frame, text="Use Custom Address", command=self.set_custom_location, font=("Segoe UI", 12)
        )
        self.btn_set_custom_loc.pack(side="left", expand=True, padx=(0, 2))

        self.btn_set_uka_tarsadia = ctk.CTkButton(
            self.location_button_frame, text="Use Uka Tarsadia", command=self.set_uka_tarsadia_for_sos, font=("Segoe UI", 12)
        )
        self.btn_set_uka_tarsadia.pack(side="left", expand=True, padx=2)

        self.btn_use_current_loc = ctk.CTkButton(
            self.location_button_frame, text="Use Current Location", command=self.set_current_location_for_sos, font=("Segoe UI", 12)
        )
        self.btn_use_current_loc.pack(side="left", expand=True, padx=(2, 0))

        self.sos_location_label = ctk.CTkLabel(self.sos_frame, text=f"SOS will use: {self.app_state.sos_location_name}", font=("Segoe UI", 12), text_color="cyan")
        self.sos_location_label.pack(pady=(10,0))


        self.btn_sos = ctk.CTkButton(self, text="[SOS] EMERGENCY SOS", command=self.send_emergency_whatsapp, 
                                          fg_color="#d32f2f", hover_color="#9a0007", height=45, font=("Segoe UI", 16, "bold"))
        self.btn_sos.pack(pady=10)

        self.progressbar = ctk.CTkProgressBar(self, width=400)
        self.progressbar.pack(pady=(5, 10))
        self.progressbar.set(0)

        # START PERFORMANCE THREADS
        threading.Thread(target=self.location_monitor, daemon=True).start()
        threading.Thread(target=self.setup_tray, daemon=True).start()

    def _format_place_details(self, place: dict) -> str:
        """Formats a place dictionary into a readable string for the UI."""
        name = place.get('name', 'Unnamed Business')
        address = place.get('address', 'N/A')
        categories = place.get('categories', [])
        lat, lon = place.get('lat'), place.get('lon')

        # Format categories nicely: "catering.restaurant" -> "Restaurant"
        category_str = ", ".join([cat.split('.')[-1].replace('_', ' ').title() for cat in categories]) if categories else "N/A"

        details = [f"-> {name}"]
        details.append(f"  Address: {address}")
        details.append(f"  Categories: {category_str}")
        if lat and lon:
            maps_url = f"https://www.google.com/maps?q={lat},{lon}"
            details.append(f"  Map: {maps_url}")
        return "\n".join(details)

    def _get_device_coords(self):
        """Fetches device coordinates from Windows location services when available."""
        ps_script = (
            "Add-Type -AssemblyName System.Device; "
            "$watcher = New-Object System.Device.Location.GeoCoordinateWatcher; "
            "$ok = $watcher.TryStart($false, [TimeSpan]::FromSeconds(4)); "
            "if ($ok -and -not $watcher.Position.Location.IsUnknown) { "
            "$loc = $watcher.Position.Location; "
            "Write-Output ($loc.Latitude.ToString() + ',' + $loc.Longitude.ToString()) }"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=7
            )
            output = (result.stdout or "").strip()
            if not output:
                return None
            lat_str, lon_str = output.split(",", 1)
            return (float(lat_str), float(lon_str))
        except (subprocess.SubprocessError, ValueError):
            return None

    def _get_ip_coords(self):
        """Fetches approximate coordinates from an IP geolocation service."""
        try:
            resp = requests.get("https://ipapi.co/json/", headers={"User-Agent": "Spotter/1.0"}, timeout=5)
            resp.raise_for_status()  # Will raise an exception for 4xx/5xx status
            data = resp.json()
            if 'latitude' in data and 'longitude' in data:
                return (float(data['latitude']), float(data['longitude']))
            else:
                self.log_to_ui("Geolocation error: Invalid data format from API.")
                return None
        except requests.exceptions.RequestException as e:
            self.log_to_ui(f"Network error fetching coordinates: {e}")
            return None
        except (ValueError, KeyError) as e:
            self.log_to_ui(f"Error parsing coordinate data: {e}")
            return None

    def get_coords_with_source(self):
        """Returns (coords, source) where source is 'device' or 'ip'."""
        device_coords = self._get_device_coords()
        if device_coords:
            return device_coords, "device"

        ip_coords = self._get_ip_coords()
        if ip_coords:
            return ip_coords, "ip"

        return None, None

    def get_coords(self):
        coords, _ = self.get_coords_with_source()
        return coords

    def location_monitor(self):
        while not self.stop_event.is_set():
            coords, source = self.get_coords_with_source()
            if coords:
                try:
                    address_info = geoapify_api.reverse_geocode(coords[0], coords[1])
                    display_text = f"Current Location: {address_info.get('address', 'N/A')}"
                    if address_info.get('city'):
                        display_text += f", {address_info.get('city')}"
                except geoapify_api.GeoapifyError as e:
                    self.log_to_ui(f"[API Error] Reverse geocode failed: {e}")
                    display_text = f"Lat: {coords[0]:.4f} | Lon: {coords[1]:.4f}"

                if source == "ip":
                    display_text += " (IP-based approx)"
                self.after(0, lambda text=display_text: self.coords_display.configure(text=text))

                moved_far_enough = self.app_state.last_coords is None or haversine(self.app_state.last_coords, coords) > DISCOVERY_RADIUS_KM
                cooldown_elapsed = (time.time() - self.app_state.last_discovery_time) >= DISCOVERY_COOLDOWN_SEC

                if moved_far_enough and cooldown_elapsed:
                    self.perform_discovery(coords)
                    self.app_state.last_coords = coords
                    self.app_state.last_discovery_time = time.time()
            else:                self.log_to_ui("Could not retrieve current location. Retrying shortly.")
            
            self.stop_event.wait(LOCATION_POLL_INTERVAL_SEC)
    # DISCOVERY ENGINE (FIXED FOR ALL ESSENTIALS)
    def perform_discovery(self, coords):
        self.after(0, self.progressbar.start)
        categories = [
            "catering.restaurant",
            "healthcare.hospital",
            "service.vehicle.fuel",
            "healthcare.pharmacy"
        ]
        try:
            places = geoapify_api.search_places(
                latitude=coords[0],
                longitude=coords[1],
                categories=categories,
                radius=5000,
                limit=10
            )

            if places:
                self.log_to_ui(f"Scan complete. Found {len(places)} essential services:")
                for place in places:
                    self.log_to_ui(self._format_place_details(place))
            else:  # places is an empty list
                self.log_to_ui("No essential services found in a 5km radius.")
        except geoapify_api.GeoapifyError as e:
            self.log_to_ui(f"[API Error] Could not fetch nearby places: {e}")
        finally:
            self.after(0, self.progressbar.stop)

    def log_to_ui(self, msg):
        self.after(0, lambda m=msg: self.textbox.insert("end", f"[{time.strftime('%H:%M')}] {m}\n"))
        self.after(0, lambda: self.textbox.see("end"))

    def set_custom_location(self):
        dialog = ctk.CTkInputDialog(text="Enter a custom address or place:", title="Set Custom SOS Location")
        address = dialog.get_input()

        if not address or not address.strip():
            # User cancelled or entered empty string
            self.log_to_ui("Custom location entry cancelled.")
            return

        self.log_to_ui(f"Searching for: '{address}'...")
        
        def run_search():
            try:
                candidates = geoapify_api.search_address_candidates(address)
                self.after(0, lambda: self._process_search_results(candidates, address))
            except geoapify_api.GeoapifyError as e:
                self.log_to_ui(f"[API Error] Address search failed: {e}")
                self.after(0, lambda: messagebox.showerror("API Error", f"Could not search for address: {e}"))
        
        threading.Thread(target=run_search, daemon=True).start()

    def _process_search_results(self, candidates, query):
        if not candidates:
            self.log_to_ui(f"[X] No results found for '{query}'.")
            messagebox.showerror("Search Failed", f"Could not find address: '{query}'")
            return
        
        if len(candidates) == 1:
            self._apply_custom_location(candidates[0])
        else:
            self._open_selection_window(candidates)

    def _open_selection_window(self, candidates):
        top = ctk.CTkToplevel(self)
        top.title("Select Location")
        top.geometry("500x400")
        top.attributes("-topmost", True)
        
        ctk.CTkLabel(top, text="Multiple locations found. Select the correct one:", font=("Segoe UI", 14, "bold")).pack(pady=10)
        
        scroll = ctk.CTkScrollableFrame(top)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        for cand in candidates:
            btn = ctk.CTkButton(
                scroll, 
                text=cand['formatted'], 
                anchor="w",
                fg_color="transparent", 
                border_width=1,
                text_color=("black", "white"),
                command=lambda c=cand, w=top: [self._apply_custom_location(c), w.destroy()]
            )
            btn.pack(fill="x", pady=2)

    def _apply_custom_location(self, candidate):
        self.app_state.sos_coords = (candidate['lat'], candidate['lon'])
        self.app_state.sos_location_name = candidate['formatted']
        self.sos_location_label.configure(text=f"SOS will use: {self.app_state.sos_location_name}")
        self.log_to_ui(f"[OK] Custom SOS location set to: {candidate['formatted']}")

    def set_current_location_for_sos(self):
        self.app_state.sos_coords = None
        self.app_state.sos_location_name = "your current location"
        self.sos_location_label.configure(text=f"SOS will use: {self.app_state.sos_location_name}")
        self.log_to_ui("[OK] SOS location reset to your current location.")

    def set_uka_tarsadia_for_sos(self):
        self.app_state.sos_coords = UKA_TARSADIA_COORDS
        self.app_state.sos_location_name = UKA_TARSADIA_NAME
        self.sos_location_label.configure(text=f"SOS will use: {self.app_state.sos_location_name}")
        self.log_to_ui(f"[OK] SOS location set to: {UKA_TARSADIA_NAME}")

    def send_emergency_whatsapp(self):
        def run():
            # Determine the exact coordinates and location name BEFORE confirmation.
            coords = self.app_state.sos_coords or self.get_coords() or self.app_state.last_coords
            location_name_for_sos = self.app_state.sos_location_name

            if not coords:
                self.log_to_ui("SOS Error: Could not determine location.")
                self.after(0, lambda: messagebox.showerror("SOS Error", "Could not determine location."))
                return

            confirmed = messagebox.askyesno(
                title="Confirm SOS Action",
                message=f"Send '{location_name_for_sos}' to emergency contacts?",
                icon='warning'
            )

            if confirmed:
                self.log_to_ui(f"[OK] SOS Confirmed. Using '{location_name_for_sos}'.")
                lat, lon = coords
                maps_url = f"https://www.google.com/maps?q={lat},{lon}"
                message = f"[SOS] EMERGENCY! I am at: {maps_url}"
                encoded = urllib.parse.quote(message)
                
                for phone in EMERGENCY_PHONES:
                    webbrowser.open(f"https://wa.me/{phone}?text={encoded}")
            else:
                self.log_to_ui("SOS cancelled.")
        
        threading.Thread(target=run, daemon=True).start()

    def manual_check(self):
        self.log_to_ui("[SCAN] Manual scan triggered...")
        def run():
            coords = self.get_coords()
            if coords:
                self.perform_discovery(coords)
            else:
                self.log_to_ui("Manual scan failed: No location.")
        threading.Thread(target=run, daemon=True).start()

    def check_emergency_numbers_config(self):
        """Warns the user if they are using the default emergency number."""
        # This default must match the one in the module-level setup
        default_number = "918153038559"
        if EMERGENCY_PHONES_STR == default_number:
            warning_msg = (
                "!! WARNING: Using default emergency number. "
                "Please create a .env file and set your own EMERGENCY_NUMBERS."
            )
            self.log_to_ui(warning_msg)
            self.after(500, lambda: messagebox.showwarning(
                "Configuration Warning",
                "You are using the default emergency contact number. Please edit your .env file to set your own contacts."
            ))
    # SYSTEM TRAY
    def minimize_to_tray(self):
        self.withdraw()

    def restore(self, icon, item):
        self.after(0, self.deiconify)

    def setup_tray(self):
        logo_path = "logo.png"
        try:
            if not os.path.exists(logo_path):
                self.log_to_ui("logo.png not found, creating a default one.")
                Image.new('RGB', (64, 64), color='black').save(logo_path)
            icon_img = Image.open(logo_path)
        except Exception as e:
            self.log_to_ui(f"Error loading tray icon: {e}")

        menu = pystray.Menu(
            pystray.MenuItem("Show Spotter", self.restore),
            pystray.MenuItem("Exit", self.quit_all)
        )
        self.tray_icon = pystray.Icon("Spotter", icon_img, "Spotter", menu)
        self.tray_icon.run()

    def quit_all(self, icon, item):
        self.stop_event.set()
        self.tray_icon.stop()
        self.destroy()

if __name__ == "__main__":
    app = SpotterApp()
    app.mainloop()

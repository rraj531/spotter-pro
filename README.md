# Spotter Pro

Spotter Pro is a Python-based location awareness application that monitors your movement and automatically discovers essential services (hospitals, pharmacies, restaurants) nearby using the Geoapify API. It includes a system tray integration and a quick SOS feature for emergency situations.

## Features

- **Real-time Location Monitoring**: Uses Windows Location Services or IP geolocation.
- **Automatic Discovery**: Scans for essential services every 500 meters.
- **SOS Emergency System**: Quickly sends your location to predefined WhatsApp contacts.
- **Custom Locations**: Set manual SOS targets via address search.
- **System Tray**: Runs quietly in the background.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Create a `.env` file in the root directory and add your keys:
   ```env
   GEOAPIFY_API_KEY=your_api_key_here
   EMERGENCY_NUMBERS=91XXXXXXXXXX,91YYYYYYYYYY
   ```
3. Run the application:
   ```bash
   python main.pyw
   ```

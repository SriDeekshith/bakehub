from dronekit import connect, VehicleMode, LocationGlobalRelative
import firebase_admin
from firebase_admin import credentials, db
import geopy.distance
import time
import argparse

# =====================================================
# FIREBASE SETUP
# =====================================================

cred = credentials.Certificate("serviceAccountKey.json")

firebase_admin.initialize_app(cred, {
    "databaseURL": "https://bakehub-6f528-default-rtdb.firebaseio.com/"
})

delivery_ref = db.reference("delivery_requests")

print("🚁 Drone System Started... Listening for missions...", flush=True)

# =====================================================
# CONNECT TO DRONE
# =====================================================

def connectMyCopter():
    parser = argparse.ArgumentParser()
    parser.add_argument('--connect')
    args = parser.parse_args()

    print("🔌 Connecting to drone...", flush=True)

    vehicle = connect(args.connect, baud=57600, wait_ready=True)

    print("✅ Drone Connected", flush=True)
    return vehicle


vehicle = connectMyCopter()

# =====================================================
# CONFIG
# =====================================================

HOME_LAT = 16.565980
HOME_LON = 81.521722

FLIGHT_ALT = 10
HOVER_TIMEOUT = 30
ARRIVAL_THRESHOLD = 5

LOCATION_MAP = {
    "Shiva, , Shiva, Shiva - 555555": (16.565946, 81.521744),
    "BOYS": (16.566500, 81.522200),
    "GIRLS": (16.567000, 81.523000)
}

# =====================================================
# DISTANCE
# =====================================================

def get_distance(a, b):
    return geopy.distance.geodesic(a, b).meters


# =====================================================
# ARM AND TAKEOFF
# =====================================================

def arm_and_takeoff(target_alt):

    print("Checking vehicle readiness...", flush=True)

    while not vehicle.is_armable:
        print("Waiting for drone to become armable...", flush=True)
        time.sleep(1)

    vehicle.mode = VehicleMode("GUIDED")
    vehicle.armed = True

    while not vehicle.armed:
        print(vehicle.armed)
        print("Arming...", flush=True)
        time.sleep(1)

    print("Taking off...", flush=True)

    vehicle.simple_takeoff(target_alt)

    while True:
        alt = vehicle.location.global_relative_frame.alt
        print("Altitude:", alt, flush=True)

        if alt >= target_alt * 0.95:
            print("Takeoff complete", flush=True)
            break

        time.sleep(1)


# =====================================================
# GOTO
# =====================================================

def goto_location(lat, lon):

    print("Flying to:", lat, lon, flush=True)

    target = LocationGlobalRelative(lat, lon, FLIGHT_ALT)
    vehicle.simple_goto(target)

    while True:

        current = (
            vehicle.location.global_relative_frame.lat,
            vehicle.location.global_relative_frame.lon
        )

        distance = get_distance(current, (lat, lon))

        print("Distance:", distance, flush=True)

        if distance <= ARRIVAL_THRESHOLD:
            print("Arrived at location", flush=True)
            break

        time.sleep(1)


# =====================================================
# RETURN HOME
# =====================================================

def return_to_home():

    print("Returning home...")
    mission_ref.update({
                "drone_status": "returning_home"
            })
    vehicle.mode = VehicleMode("GUIDED")
    time.sleep(2)

    if vehicle.location.global_relative_frame.alt < 2:
        arm_and_takeoff(FLIGHT_ALT)

    goto_location(HOME_LAT, HOME_LON)

    vehicle.mode = VehicleMode("LAND")

    while vehicle.location.global_relative_frame.alt > 0.2:
        time.sleep(1)

    print("Landed at home")
# =====================================================
# MAIN
# =====================================================

try:

    while True:

        print("Searching for mission...", flush=True)

        missions = delivery_ref.get()

        if missions:
            print("Mission received", flush=True)
            break

        time.sleep(2)

    for order_id, mission in missions.items():

        mission_ref = delivery_ref.child(order_id)

        drone_status = mission.get("drone_status")
        location_name = mission.get("locationName")
        takeoff_permission = mission.get("takeoff_permission")
        return_permission=mission.get("return_permission")

        print("Order:", order_id, flush=True)
        print("Drone Status:", drone_status, flush=True)
        print("Location:", location_name, flush=True)
        print("Return:",return_permission ,flush =True)

        # Wait for armable
        while not vehicle.is_armable:
            print("Waiting for vehicle to become armable...", flush=True)
            time.sleep(1)

        print("Vehicle Armable", flush=True)

        # Activate takeoff button
        if takeoff_permission != "Activate":

            print("Activating takeoff permission", flush=True)

            mission_ref.update({
                "takeoff_permission": "Activate"
            })

        # Wait for trigger
        while True:

            mission = mission_ref.get()
            takeoff_triggered = mission.get("takeoff_triggered")

            if takeoff_triggered:
                print("Takeoff trigger received", flush=True)
                break

            print("Waiting for takeoff trigger...", flush=True)
            time.sleep(1)

        drone_status = mission.get("drone_status")

        if True :

            print("Starting mission:", order_id, flush=True)

            if location_name not in LOCATION_MAP:

                print("Unknown location. Deleting order.", flush=True)
                mission_ref.delete()
                continue

            mission_ref.update({
                "drone_status": "taking_off"
            })

            arm_and_takeoff(FLIGHT_ALT)

            mission_ref.update({
                "drone_status": "flying"
            })

            lat, lon = LOCATION_MAP[location_name]

            goto_location(lat, lon)

            mission_ref.update({
                "drone_status": "hovering",
                "landing_permission": "Activate"
            })

            print("Hovering... waiting for landing trigger", flush=True)

            start_time = time.time()
            landed = False

            while True:

                mission = mission_ref.get()
                landing_triggered = mission.get("landing_triggered")

                if landing_triggered:
                    landed = True
                    print("landing triggered")
                    break

                if time.time() - start_time > HOVER_TIMEOUT:
                    print("Hover timeout reached", flush=True)
                    break

                time.sleep(1)

            if landed:

                mission_ref.update({
                    "drone_status": "landing"
                })

                vehicle.mode = VehicleMode("LAND")

                while vehicle.location.global_relative_frame.alt > 0.2:
                    time.sleep(1)

                print("Delivery completed", flush=True)

                mission_ref.update({
                
                "return_permission": "Activate"
            })
                start = time.time()

                while True:

                    mission = mission_ref.get()
                    return_triggered = mission.get("return_triggered")

                    if return_triggered:
                        print("RTH Triggered")
                        return_to_home()
                        break

                    if time.time() - start > 300:
                        print("Return timeout -> Auto RTH")
                        return_to_home()
                        break

                    time.sleep(1)
                


            else:

                print("Landing not triggered", flush=True)
                mission_ref.update({
                    "return_by":"Drone"
                })
                return_to_home()

           
            
            print("Clearing order...", flush=True)

            mission_ref.delete()

            print("Mission completed successfully", flush=True)

except Exception as e:

    print("Error:", e, flush=True)

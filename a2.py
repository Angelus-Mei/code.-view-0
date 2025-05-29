'''
game.py — Space Exploration Game Module
The game module runs the space exploration game.
It coordinates gameplay by integrating the map functionality from space_map.py
and the Ship class from ship.py. This module initialises the space exploration
map and ship, and runs the game where players issue commands to explore the
map, interact with entities, and aim to reach the destination.
'''
from space_map import create_map, display_map, populate_map
from ship import Ship
# import your 2 files here!
def main():
    '''
    Runs the entire program from start to end.

    All program logic must be executed within the main() function. We have
    provided some starting implementation and comments to help you out.
    '''
    print('>>> STARTING ROUTE: Kepler-452b -> Sector 9-Delta\n')
    # 1. Configuring navigation systems
    # - Ask for size of map
    # - Then use this size to create a map reusing functions from the space_map
    #   module!
    # ...
    print(">> CONFIGURING NAVIGATIONAL SYSTEMS")
    while True:
        try:
            size = int(input("Enter size of map (n >= 2): "))
            if size>=2:
                break
            else:
                print("Error: n too low")
        except ValueError:
            print("Error: Invalid input. Please enter an integer.")
    game_map = create_map(size)
    populate_map(game_map)
    print(f"{size} x {size} map initialised.\n")
    display_map(game_map)
    print()
    print(">> NAVIGATIONAL SYSTEMS READY\n")
    # 2. Configuring ship systems
    # - Ask for name and fuel of ship
    # - Then using the name and fuel, create a Ship instance reusing the Ship
    #   class from the ship module!
    # ...
    print(">> CONFIGURING SHIP SYSTEMS")
    ship_name = input("Enter ship name: ")
    while True:
        try:
            fuel=int(input("Enter fuel (1-99): "))
            if 1<=fuel<=99:
                break
            elif fuel < 1:
                print("Error: fuel too low")
            else:
                print("Error: fuel too high")
        except ValueError:
            print("Error: Invalid input. Please enter an integer.")
    odyssey=Ship(ship_name,fuel)
    odyssey.x,odyssey.y=0,0
    odyssey.put_x,odyssey.put_y=0,0
    print(odyssey)
    print(">> SHIP SYSTEMS READY\n")
    print(">>> EXECUTING LIFTOFF: EXITING Kepler-452b's ORBIT\n")
    print('>>> AWAITING COMMANDS\n')
    # 3. Game Loop
    # - At this stage, you should have both a map and ship initialised
    # - Take in commands from user to navigate map and progress the game
    # - You'll need to make frequent use of both your map and ship!
    #   - Your ship stores (x, y): This is [y][x] on the map!
    #   - When you find where the ship wants to move, call its interact()
    #     method!
    # - After each interaction, you'll need to check win/loss conditions
    #   - Check if ship reached destination (remember ship stores this!)
    #   - Check if ship has no health
    #   - Check if ship has no fuel left
    # ...
    while True:
        cmd=input("Enter (n,e,s,w | map | status): ").lower()
        if cmd == "q":
            print(f"{odyssey.name} has self-destructed.")
            game_map[odyssey.y][odyssey.x] = "L"
            display_map(game_map)
            print("\n>>> MISSION FAILED")
            break
        elif cmd=="map":
            display_map(game_map)
        elif cmd =="status":
            print(odyssey)
        elif cmd in ["n","e","s","w"]:
            new_x,new_y=odyssey.x,odyssey.y
            if cmd=="n":
                new_y-=1
            elif cmd=="e":
                new_x+=1
            elif cmd=="s":
                new_y+=1
            elif cmd=="w":
                new_x-=1

            if 0<=new_x<size and 0<=new_y<size:
                target=game_map[new_y][new_x]
                result=odyssey.interact(target, new_x, new_y)
                if result:
                    old_x, old_y = odyssey.x, odyssey.y
                    game_map[old_y][old_x] = " "
                    odyssey.x, odyssey.y = new_x, new_y
                    game_map[odyssey.y][odyssey.x] = "@"
                    if target=="X":
                        print(f"{odyssey.name} has reached: Sector 9-Delta")
                        game_map[odyssey.y][odyssey.x] = "W"
                        display_map(game_map)
                        print("\n>>> MISSION COMPLETED")
                        break
                    elif odyssey.is_out_of_health():
                        print(f"{odyssey.name} has fallen.")
                        game_map[odyssey.y][odyssey.x]="L"
                        display_map(game_map)
                        print("\n>>> MISSION FAILED")
                        break
                    elif odyssey.is_out_of_fuel():
                        print(f"{odyssey.name} is out of fuel.")
                        game_map[odyssey.y][odyssey.x]="L"
                        display_map(game_map)
                        print("\n>>> MISSION FAILED")
                        break
            else:
                print("Error: out of bounds")
        else:
            print("Error: unrecognised command")
if __name__ == '__main__':
    main()
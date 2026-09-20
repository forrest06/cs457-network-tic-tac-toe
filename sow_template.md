# CS 457 Sprint 0 Statement of Work

Forrest Fisher | CS 457 - Computer Networks | September 19, 2026

## Project idea

For my final project, I am making a two-player network Tic-Tac-Toe game that runs in the command line. Two players will connect to one central server from separate client computers. The server will keep the official game board, check each move, and send the updated board to both players.

I chose Tic-Tac-Toe because the rules are simple, but the project still gives me a good way to practice sockets, client-server communication, turn handling, and keeping both clients synchronized.

## Game rules

- The first player to connect will be Player 1 and use X.
- The second player to connect will be Player 2 and use O.
- X goes first. The players then alternate turns.
- On each turn, the player chooses an empty square numbered 1 through 9.
- The server rejects a move if it is out of turn, outside the range 1-9, or placed in an occupied square. An invalid move does not use up the player's turn.
- A player wins by placing three matching marks in a row, column, or diagonal.
- The game is a draw when all nine squares are filled and neither player has won.
- If one player disconnects before the game ends, the other player wins by forfeit.

## Development plan

I will write the project in Python 3 and use TCP sockets. Messages between the clients and server will use simple JSON so the data is easy to read and test. The server will be responsible for assigning players, enforcing turns, checking moves, and deciding when the game is over.

My basic development order will be:

1. Write and test the Tic-Tac-Toe game logic.
2. Create the server and connect two clients.
3. Add turn enforcement and board updates.
4. Handle invalid moves and disconnects.
5. Test the game locally and then deploy it in CML.

For the CML setup, the two clients and server will be placed on separate network segments. The clients will connect using the server's DNS name instead of a hard-coded IP address. I will capture DHCP, DNS, and game traffic with Wireshark during the later networking sprints.

## Repository and server name

The project will be tracked in a public GitHub repository. The repository includes a Python `.gitignore`, basic editor settings, and separate folders for source code, tests, and documentation. I will use commits to track each project milestone.

Public repository: https://github.com/forrest06/cs457-network-tic-tac-toe

Authoritative DNS domain: `server.fisher.edu`

sudo tc qdisc add dev lo root netem delay 1ms
sudo tc qdisc del dev lo root

sudo ip route add 10.10.10.0/24 via 127.0.0.1

sudo ip route del 10.10.10.0/24

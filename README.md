# broadlink6

IPv6-capable client for Broadlink RM-series devices (RM4 mini/pro framing).

Broadlink firmware is IPv4-only, but nothing about the wire protocol requires
the client to be: this library speaks the same UDP protocol over IPv6 sockets,
so an IPv6-only host can reach a device through NAT64 (for example via the
DNS64-synthesized address of the device's IPv4 reservation). The hello
packet's embedded local-IPv4 field is sent zeroed — devices reply to the UDP
source address and ignore it.

Supported operations: discovery/identity (`hello`), session authentication,
IR transmission from raw packets or microsecond pulse sequences, IR learning,
and the built-in temperature/humidity sensors.

```python
import broadlink6

info = broadlink6.hello("64:ff9b::a00:2804")
device = broadlink6.Device("64:ff9b::a00:2804", info.devtype, info.mac)
device.auth()
device.send_pulses([4350, 4350, 550, 1550, 550, 550])
```

The protocol layout follows the reference implementation in
[python-broadlink](https://github.com/mjg59/python-broadlink) (MIT).

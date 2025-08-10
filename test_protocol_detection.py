#!/usr/bin/env python3
"""
Test script to verify protocol detection and filtering functions.
"""

import sys
from pathlib import Path
from scapy.all import Ether, IPv6, TCP, Packet
from scapy.layers.l2 import Dot1Q

# Add the experiment_utils path
sys.path.append(str(Path(__file__).parent))

# Import the functions we want to test
from experiment_utils.draw.draw_pcap import (
    is_isis_packet, is_ospf6_packet, is_bgp_packet,
    ProtocolType, ProtocolInfo, extract_protocol_details
)


def test_isis_detection():
    """Test ISIS packet detection."""
    print("Testing ISIS packet detection...")
    
    # Create a test packet with ISIS EtherType
    isis_packet = Ether(type=0x22F0) / b'\x83\x00\x00\x00'  # NLPID 0x83 for ISIS
    result = is_isis_packet(isis_packet)
    print(f"ISIS EtherType test: {'PASS' if result else 'FAIL'}")
    
    # Test VLAN tagged ISIS packet
    vlan_isis_packet = Ether() / Dot1Q(type=0x22F0) / b'\x83\x00\x00\x00'
    result = is_isis_packet(vlan_isis_packet)
    print(f"VLAN ISIS test: {'PASS' if result else 'FAIL'}")
    
    # Test non-ISIS packet
    non_isis_packet = Ether(type=0x0800) / b'\x45\x00\x00\x00'  # IP packet
    result = is_isis_packet(non_isis_packet)
    print(f"Non-ISIS test: {'PASS' if not result else 'FAIL'}")


def test_ospf6_detection():
    """Test OSPFv6 packet detection."""
    print("\nTesting OSPFv6 packet detection...")
    
    # Create a test IPv6 packet with OSPF next header (89)
    ospf6_packet = IPv6(nh=89) / b'\x03\x01\x00\x00'  # OSPF version 3, Hello type
    result = is_ospf6_packet(ospf6_packet)
    print(f"OSPFv6 IPv6 nh=89 test: {'PASS' if result else 'FAIL'}")
    
    # Test non-OSPF packet
    non_ospf_packet = IPv6(nh=6) / TCP()  # TCP packet
    result = is_ospf6_packet(non_ospf_packet)
    print(f"Non-OSPFv6 test: {'PASS' if not result else 'FAIL'}")


def test_bgp_detection():
    """Test BGP packet detection."""
    print("\nTesting BGP packet detection...")
    
    # Create a test TCP packet on port 179
    bgp_packet = IPv6() / TCP(sport=179, dport=1024)
    result = is_bgp_packet(bgp_packet)
    print(f"BGP TCP port 179 test: {'PASS' if result else 'FAIL'}")
    
    # Test destination port 179
    bgp_packet2 = IPv6() / TCP(sport=1024, dport=179)
    result = is_bgp_packet(bgp_packet2)
    print(f"BGP TCP dport 179 test: {'PASS' if result else 'FAIL'}")
    
    # Test non-BGP packet
    non_bgp_packet = IPv6() / TCP(sport=80, dport=8080)
    result = is_bgp_packet(non_bgp_packet)
    print(f"Non-BGP test: {'PASS' if not result else 'FAIL'}")


def test_protocol_details_extraction():
    """Test protocol details extraction."""
    print("\nTesting protocol details extraction...")
    
    # Test with a simple packet for each protocol type
    test_packet = Ether(type=0x22F0) / b'\x83\x00\x00\x00'
    
    # Test ISIS details
    isis_info = ProtocolInfo(protocol_type=ProtocolType.ISIS)
    isis_details = extract_protocol_details(test_packet, isis_info)
    print(f"ISIS details extraction: {'PASS' if isinstance(isis_details, dict) else 'FAIL'}")
    
    # Test OSPFv6 details
    ospf6_packet = IPv6(nh=89) / b'\x03\x01\x00\x00'
    ospf6_info = ProtocolInfo(protocol_type=ProtocolType.OSPF6)
    ospf6_details = extract_protocol_details(ospf6_packet, ospf6_info)
    print(f"OSPFv6 details extraction: {'PASS' if isinstance(ospf6_details, dict) else 'FAIL'}")
    
    # Test BGP details
    bgp_packet = IPv6() / TCP(sport=179)
    bgp_info = ProtocolInfo(protocol_type=ProtocolType.BGP)
    bgp_details = extract_protocol_details(bgp_packet, bgp_info)
    print(f"BGP details extraction: {'PASS' if isinstance(bgp_details, dict) else 'FAIL'}")


def main():
    """Run all tests."""
    print("Protocol Detection and Filtering Test Suite")
    print("=" * 50)
    
    try:
        test_isis_detection()
        test_ospf6_detection()
        test_bgp_detection()
        test_protocol_details_extraction()
        
        print("\n" + "=" * 50)
        print("Test suite completed!")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
"""Package-level checks for the seven-74 replacement, independent of CPU decode."""
import pytest

from simulators.cyclesim.hybrid.cupl_model import bits,number
from simulators.cyclesim.hybrid.ram_no1502 import PageDecode74,replacement_packages


@pytest.mark.parametrize('mode',[0,1])
def test_ram_no1502_decode_entire_address_space(mode):
    """All 65,536 addresses per mode; bounded, below the default 30s limit."""
    page=PageDecode74()
    for address in range(65536):
        actual=page.decode(address,mode)
        # Independent memory-map ranges, not the NAND/decode implementation.
        mailbox=0xFF00<=address<0xFFFC
        rom=not mode and (address<0x800 or address>=0xFFFC)
        ram=not (mailbox or rom)
        assert actual==dict(romn=int(not rom),mbn=int(not mailbox),
                            ram0n=int(not (ram and address<0x8000)),
                            ram1n=int(not (ram and address>=0x8000)))


def test_ram_no1502_173_load_hold_reset_and_output_enables():
    page=PageDecode74()
    for data in range(256):
        for hold in (0,1):
            previous=dict(page.state)
            values=page.values(dict(reset=0,execute=0,pload=hold,mapmode=1,**bits('db',data,8)))
            page.state=page.next(values)
            assert page.state==(previous if hold else bits('page',data,8))
        off=page.values(dict(reset=0,execute=1,pload=1,mapmode=1))
        assert all(off[f'addr{i}_oe']==0 for i in range(8,16))
    reset=page.values(dict(reset=1,execute=0,pload=1,mapmode=1,**bits('db',255,8)))
    assert all(reset[f'addr{i}']==0 for i in range(8,16))
    page.state=page.next(reset)
    assert number(page.state,'page',8)==0


def test_ram_no1502_decoder_uses_exported_connections():
    page=PageDecode74()
    assert len(replacement_packages())==7
    assert page.decode(0,0)['romn']==0
    page.packages['DEC_BOOT']['pins']['G1']='GND'
    assert page.decode(0,0)['romn']==1

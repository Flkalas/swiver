"""Define and check the comparison's pin-connection accounting boundary."""
from simulators.cyclesim.hybrid.ram_educational_measure import wiring


def test_inter_ic_connections_include_tied_signal_pins_but_exclude_power_and_jtag():
    board={'packages':[
        {'ref':'A','pins':{'Y':'bus','VCC':'VCC','GND':'GND','TDI':'A_TDI','NC':None}},
        {'ref':'B','pins':{'D0':'bus','D1':'bus','Y':'control','UNUSED':'unconnected'}},
        {'ref':'C','pins':{'D':'bus','EN':'control','ZERO':'GND'}}]}
    result=wiring(board)
    # Bus: four terminals -> three tree links. Control: two -> one.
    assert result['inter_ic_signal_nets']==2
    assert result['signal_pin_endpoints']==6
    assert result['minimum_point_to_point_links']==4
    assert result['power_and_constant_pin_endpoints']==3
    assert result['net_endpoints']['bus']==['A.Y','B.D0','B.D1','C.D']


def test_inter_ic_metric_is_independent_of_package_order():
    packages=[{'ref':'A','pins':{'Y':'data'}},
              {'ref':'B','pins':{'D':'data','EN':'enable'}},
              {'ref':'C','pins':{'Y':'enable'}}]
    first=wiring({'packages':packages})
    second=wiring({'packages':list(reversed(packages))})
    for key in ('inter_ic_signal_nets','signal_pin_endpoints','minimum_point_to_point_links'):
        assert first[key]==second[key]

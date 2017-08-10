"""All unit tests for TriCap."""

import unittest

from tests.test_basic import TimeMonitorTests
from tests.test_log_list import TestLogList
from tests.test_talkbox import TestTalkBox
from tests.test_configure import TestConfigure
from tests.test_session_logger import TestSessionLogger
from tests.test_connection_monitor import TestNetMonitor, TestNetMonLogger, TestIPMonitor
from tests.test_connection_monitor import TestIPMonLogger
from tests.test_system_monitor import TestSysMon, TestSysMonLogger
from tests.test_camera_logger import TestCameraLoggingObserver
from tests.test_dummy_alti import TestDummyAlti
from tests.test_dummy_cam import TestDummyCam
from tests.test_alti_simulator import TestAltiSimulator
from tests.test_altitude_switch import TestAltiSwitch
from tests.test_page_home import TestHome
if __name__ == '__main__':
    unittest.main()

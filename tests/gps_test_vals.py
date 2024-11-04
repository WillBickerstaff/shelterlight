import datetime as dt
from shelterGPS.common import GPSDir

# Chat GPT used to generate test message.
# GPT messages included incorrect checksums, validated at:
# https://nmeachecksum.eqth.net/
valid_NMEA = [
        # GGA - GPS (GP)
        "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47",
        "$GPGGA,104230,3723.5478,S,12218.8765,W,1,07,1.0,10.2,M,0.0,M,,*43",
        "$GPGGA,152310,2503.1234,N,12134.5678,E,1,09,0.8,55.7,M,10.0,M,,*78",

        # GGA - BeiDou (BD)
        "$BDGGA,091830,2233.1274,N,11404.6581,E,1,10,0.9,50.1,M,0.0,M,,*56",
        "$BDGGA,132015,3010.8765,N,10234.4321,E,1,08,0.7,70.5,M,20.0,M,,*66",
        "$BDGGA,183745,4056.7890,S,11618.8765,W,1,06,1.1,30.3,M,5.0,M,,*51",

        # GGA - GLONASS (GL)
        "$GLGGA,141920,5540.1234,N,03736.8765,E,1,06,1.2,200.3,M,39.5,M,,*57",
        "$GLGGA,112045,4523.6543,N,06234.9876,E,1,07,0.9,150.8,M,30.0,M,,*5B",
        "$GLGGA,175310,3345.7890,S,04923.1234,W,1,08,0.6,80.4,M,25.0,M,,*6A",

        # GGA - Galileo (GA)
        "$GAGGA,164500,3507.7890,N,13942.1234,E,1,09,0.8,75.4,M,15.0,M,,*68",
        "$GAGGA,102530,2245.1234,N,01334.8765,E,1,08,1.0,90.2,M,18.0,M,,*61",
        "$GAGGA,201815,5043.5678,N,01623.6543,E,1,10,0.7,110.5,M,12.0,M,,*50",

        # GGA - Mixed Constellation (GN)
        "$GNGGA,102030,3723.5478,S,14515.8765,E,1,12,0.6,120.0,M,18.0,M,,*4D",
        "$GNGGA,135040,4745.6789,N,08312.5432,W,1,09,0.9,60.1,M,14.0,M,,*75",
        "$GNGGA,225540,5810.8765,S,00345.9876,E,1,11,1.1,95.8,M,20.0,M,,*71",

        # RMC - GPS (GP)
        "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A",
        "$GPRMC,225446,A,5123.456,N,01234.567,E,054.7,089.5,150998,004.4,E*79",
        "$GPRMC,153032,A,3402.678,S,05823.123,W,018.5,250.7,250601,006.8,W*6F",

        # RMC - BeiDou (BD)
        "$BDRMC,142350,A,2456.789,N,11458.123,E,008.3,203.5,310721,001.2,W*74",
        "$BDRMC,063415,A,2234.123,S,11312.345,E,005.0,092.0,170322,003.5,E*77",
        "$BDRMC,184756,A,3210.876,N,11534.567,E,012.8,137.9,280822,002.3,W*77",

        # RMC - GLONASS (GL)
        "$GLRMC,115632,A,5532.123,N,03821.654,E,014.2,178.9,110501,000.0,W*70",
        "$GLRMC,093215,A,6043.987,S,03015.876,W,011.7,312.5,220822,001.9,E*62",
        "$GLRMC,172845,A,4955.654,N,03612.432,E,023.1,045.2,080623,002.5,E*65",

        # RMC - Galileo (GA)
        "$GARMC,201045,A,3645.123,N,14012.345,E,018.0,110.5,290522,003.0,E*64",
        "$GARMC,045700,A,2222.876,S,02434.678,W,020.4,255.8,101015,004.5,W*74",
        "$GARMC,132500,A,5055.432,N,01323.876,E,030.0,015.3,121220,005.6,E*6D",

        # RMC - Mixed Constellation (GN)
        "$GNRMC,143512,A,3723.5478,S,14515.8765,E,033.6,275.4,080923,010.2,W*65",
        "$GNRMC,224500,A,4745.6789,N,08312.5432,W,041.1,305.0,170722,009.3,E*78",
        "$GNRMC,090123,A,5810.8765,S,00345.9876,E,012.5,180.0,220921,008.0,W*61"
    ]

valid_dt = [
    # Beginning and End of Time (Year, Month, Day, Hour, Minute, Second)
    {"date": "000101", "time": "000000", "dt_obj": dt.datetime(2000, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc)},  # Start of the millennium
    {"date": "211231", "time": "235959", "dt_obj": dt.datetime(2021, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc)},  # End of the year
    {"date": "991231", "time": "235959", "dt_obj": dt.datetime(2099, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc)},  # Leap year boundary
    # Start and End of Days
    {"date": "010101", "time": "000000", "dt_obj": dt.datetime(2001, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc)},  # Just after midnight
    {"date": "010101", "time": "235959", "dt_obj": dt.datetime(2001, 1, 1, 23, 59, 59, tzinfo=dt.timezone.utc)},  # Early morning
    {"date": "011231", "time": "235959", "dt_obj": dt.datetime(2001, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc)},  # Late evening

    # Special Patterns and Palindromes
    {"date": "050505", "time": "050505", "dt_obj": dt.datetime(2005, 5, 5, 5, 5, 5, tzinfo=dt.timezone.utc)},  # Repeating pattern
    {"date": "111111", "time": "111111", "dt_obj": dt.datetime(2011, 11, 11, 11, 11, 11, tzinfo=dt.timezone.utc)},  # All ones
    {"date": "090909", "time": "090909", "dt_obj": dt.datetime(2009, 9, 9, 9, 9, 9, tzinfo=dt.timezone.utc)},  # All nines

    # Symmetrical and Unique Time Patterns
    {"date": "200220", "time": "022020", "dt_obj": dt.datetime(2020, 2, 20, 2, 20, 20, tzinfo=dt.timezone.utc)},  # Symmetrical date and time
    {"date": "121212", "time": "121212", "dt_obj": dt.datetime(2012, 12, 12, 12, 12, 12, tzinfo=dt.timezone.utc)},  # Repeating number pattern
    {"date": "111213", "time": "111213", "dt_obj": dt.datetime(2011, 12, 13, 11, 12, 13, tzinfo=dt.timezone.utc)},  # Sequential time pattern

    # Leap and Non-Leap Year Transitions
    {"date": "230323", "time": "123456", "dt_obj": dt.datetime(2023, 3, 23, 12, 34, 56, tzinfo=dt.timezone.utc)},  # Normal year
    {"date": "220615", "time": "091530", "dt_obj": dt.datetime(2022, 6, 15, 9, 15, 30, tzinfo=dt.timezone.utc)},  # Mid-year
    {"date": "230908", "time": "164200", "dt_obj": dt.datetime(2023, 9, 8, 16, 42, 0, tzinfo=dt.timezone.utc)},  # Late summer

    # Year, Month, Day Combinations
    {"date": "231231", "time": "123123", "dt_obj": dt.datetime(2023, 12, 31, 12, 31, 23, tzinfo=dt.timezone.utc)},  # End of the month
    {"date": "220717", "time": "112233", "dt_obj": dt.datetime(2022, 7, 17, 11, 22, 33, tzinfo=dt.timezone.utc)},  # Summer day
    {"date": "210922", "time": "070809", "dt_obj": dt.datetime(2021, 9, 22, 7, 8, 9, tzinfo=dt.timezone.utc)},  # Autumn equinox

    # Random Valid Dates and Times
    {"date": "030102", "time": "010203", "dt_obj": dt.datetime(2003, 1, 2, 1, 2, 3, tzinfo=dt.timezone.utc)},
    {"date": "060504", "time": "040506", "dt_obj": dt.datetime(2006, 5, 4, 4, 5, 6, tzinfo=dt.timezone.utc)},
    {"date": "090807", "time": "070809", "dt_obj": dt.datetime(2009, 8, 7, 7, 8, 9, tzinfo=dt.timezone.utc)},
    {"date": "121110", "time": "101112", "dt_obj": dt.datetime(2012, 11, 10, 10, 11, 12, tzinfo=dt.timezone.utc)},
    {"date": "140313", "time": "131415", "dt_obj": dt.datetime(2014, 3, 13, 13, 14, 15, tzinfo=dt.timezone.utc)},
    {"date": "180716", "time": "161718", "dt_obj": dt.datetime(2018, 7, 16, 16, 17, 18, tzinfo=dt.timezone.utc)},
    {"date": "210219", "time": "192021", "dt_obj": dt.datetime(2021, 2, 19, 19, 20, 21, tzinfo=dt.timezone.utc)},
    {"date": "030405", "time": "030405", "dt_obj": dt.datetime(2003, 4, 5, 3, 4, 5, tzinfo=dt.timezone.utc)},
    {"date": "060708", "time": "060708", "dt_obj": dt.datetime(2006, 7, 8, 6, 7, 8, tzinfo=dt.timezone.utc)},
    {"date": "090101", "time": "090101", "dt_obj": dt.datetime(2009, 1, 1, 9, 1, 1, tzinfo=dt.timezone.utc)}
]

invalid_dt = [
    # Invalid Day on Its Own
    {"date": "112335", "time": "010101"},  # Day 35 is invalid
    {"date": "050045", "time": "150000"},  # Day 45 is invalid
    {"date": "091132", "time": "080000"},  # Day 32 is invalid

    # Invalid Month on Its Own
    {"date": "151315", "time": "130000"},  # Month 15 is invalid
    {"date": "020013", "time": "235959"},  # Month 00 is invalid
    {"date": "072212", "time": "004500"},  # Month 22 is invalid

    # Invalid Hour on Its Own
    {"date": "130701", "time": "250000"},  # Hour 25 is invalid
    {"date": "021519", "time": "240101"},  # Hour 24 is invalid (valid only for 00:00)
    {"date": "060616", "time": "290000"},  # Hour 29 is invalid

    # Invalid Minute on Its Own
    {"date": "040312", "time": "126100"},  # Minute 61 is invalid
    {"date": "120410", "time": "088000"},  # Minute 80 is invalid

    # Invalid Second on Its Own
    {"date": "020210", "time": "123460"},  # Second 60 is invalid
    {"date": "071901", "time": "053580"},  # Second 80 is invalid
    {"date": "031414", "time": "222500"},  # Second 500 is invalid (extreme example)

    # Combined Errors (Mix of Different Invalid Fields)
    {"date": "992331", "time": "280000"},  # Invalid day and hour
    {"date": "000033", "time": "060000"},  # Invalid day in leap year context
    {"date": "053299", "time": "150000"},  # Invalid day and second

    # February 29th on a Non-Leap Year
    {"date": "022902", "time": "120000"},  # 2002 is not a leap year
    {"date": "022901", "time": "010101"},  # 2001 is not a leap year
    {"date": "022903", "time": "230000"},  # 2003 is not a leap year

    # Invalid Format (Conceptual Issues)
    {"date": "abcd12", "time": "120000"},  # Non-numeric date
    {"date": "010120", "time": "xx2359"},  # Non-numeric time

    # Extreme Invalid Values
    {"date": "999999", "time": "999999"},  # Completely invalid date and time
    {"date": "000000", "time": "000000"},  # Conceptually invalid as a date
    {"date": "311299", "time": "245959"},  # Invalid hour for New Year's Eve
    {"date": "101010", "time": "102564"},  # Invalid second value
    {"date": "202020", "time": "888888"},  # Completely off the range

    # Overflows and Misplacements
    {"date": "062532", "time": "123060"},  # Second overflow
    {"date": "123132", "time": "142561"},  # Minute and second invalid
    {"date": "021532", "time": "255959"},  # Hour overflow
]

valid_coordinates = [
    # Edge cases near zero
    {"coord": "0000.0001", "dir": GPSDir.North, "expected": 0.0000016667},
    {"coord": "0000.0001", "dir": GPSDir.East, "expected": 0.0000016667},

    # Exact degree boundaries
    {"coord": "0100.0000", "dir": GPSDir.North, "expected": 1.0},
    {"coord": "1000.0000", "dir": GPSDir.East, "expected": 10.0},

    # Decimal precision
    {"coord": "4530.1234", "dir": GPSDir.North, "expected": 45.50205666666667},
    {"coord": "1720.9876", "dir": GPSDir.West, "expected": -17.349793333333334},

    # Minimum and maximum valid values
    {"coord": "0000.0001", "dir": GPSDir.South, "expected": -0.0000016667},
    {"coord": "8959.9999", "dir": GPSDir.North, "expected": 89.99999833333334},
    {"coord": "17959.9999", "dir": GPSDir.West, "expected": -179.99999833333334},

    # High precision decimal values
    {"coord": "1234.5678", "dir": GPSDir.North, "expected": 12.57613},
    {"coord": "0959.9999", "dir": GPSDir.East, "expected": 9.999998333333334},

    # Mixed leading zeros
    {"coord": "0034.5678", "dir": GPSDir.North, "expected": 0.57613},
    {"coord": "34.5678", "dir": GPSDir.North, "expected": 0.57613},  # Equivalent to the previous case

    # Single degree values
    {"coord": "100.0000", "dir": GPSDir.West, "expected": -1.0},
    {"coord": "100.0000", "dir": GPSDir.East, "expected": 1.0},

    # Alternate hemisphere testing
    {"coord": "4530.0000", "dir": GPSDir.North, "expected": 45.5},
    {"coord": "4530.0000", "dir": GPSDir.South, "expected": -45.5},
    {"coord": "1720.0000", "dir": GPSDir.East, "expected": 17.333333333333332},
    {"coord": "1720.0000", "dir": GPSDir.West, "expected": -17.333333333333332},

    # Boundary conditions for longitude
    {"coord": "00000.0001", "dir": GPSDir.West, "expected": -0.0000016667},
    {"coord": "17959.9999", "dir": GPSDir.East, "expected": 179.99999833333334},
    {"coord": "00000.0000", "dir": GPSDir.West, "expected": 0.0},
    {"coord": "18000.0000", "dir": GPSDir.East, "expected": 180.0},


    # Additional precision cases
    {"coord": "8500.1234", "dir": GPSDir.South, "expected": -85.00205666666666},
    {"coord": "0200.0000", "dir": GPSDir.North, "expected": 2.0},
]

invalid_coordinates = [
    {"coord": "9100.0000", "dir": GPSDir.North},  # Latitude > 90 degrees
    {"coord": "9100.0000", "dir": GPSDir.South},  # Latitude < -90 degrees
    {"coord": "18100.0000", "dir": GPSDir.East},  # Longitude > 180 degrees
    {"coord": "18100.0000", "dir": GPSDir.West},  # Longitude < -180 degrees
    {"coord": "-1234.5678", "dir": GPSDir.North}, # Negative value for North
    {"coord": "abcd.efgh", "dir": GPSDir.South},  # Non-numeric characters
]
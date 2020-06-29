Feature: Temp Control

    Scenario: Wort temperature is lower than set point temperature
        Given wort temp is 25
        And setpoint temp is 21
        Then direction is cooling

    Scenario: Bleh
        Given wort temp is 20
        And setpoint temp is 25
        Then direction is heating

    Scenario: bb
        Given ambient temp is 30
        And setpoint temp is 21
        And wort temp is 30
        Then direction is cooling
        And cooling power percent is gt 80


=== PARAGRAPH 0 ===
OLD TEXT:
UN R171 (version 1.1.0) Consolidated text of this version, rendered by Certivity for the hackathon. Cite pages of THIS file: the page number is printed at the bottom of every page. Role in the hackathon: base version. Introduction
OLD REQUIREMENTS derived from it (answer-key style):
  (none)
NEW TEXT:
UN R171 (version 2.0.0) Consolidated text of this version, rendered by Certivity for the hackathon. Cite pages of THIS file: the page number is printed at the bottom of every page. Role in the hackathon: latest version. Introduction
OUR CURRENT FLAGS for this paragraph:
  (none)

=== PARAGRAPH 1.2 ===
OLD TEXT:
This UN Regulation does not apply to the approval of vehicles with regard to their Automatically Commanded Steering Functions (ACSF) or Risk Mitigation Function (RMF) which have been approved to UN Regulation No. 79, even when a system is exercising longitudinal control at the same time. However, if the manufacturer declares such ACSF or RMF to be part of DCAS, this UN Regulation applies irrespective of whether it has also been approved to UN Regulation No. 79. 2. Definitions For the purposes of this Regulation: 2.1. _“Driver Control Assistance System (DCAS)”_ means the hardware and software collectively capable of assisting a driver in controlling the longitudinal and lateral motion of the vehicle on a sustained basis. Within this UN Regulation, DCAS is also referred to as “ _the system_ ”.
OLD REQUIREMENTS derived from it (answer-key style):
  (none)
NEW TEXT:
This UN Regulation does not apply to:
OUR CURRENT FLAGS for this paragraph:
  added : This UN Regulation shall not apply to vehicles of Categories X and Y.

=== PARAGRAPH 1.2.1 ===
OLD TEXT:
(paragraph did not exist in old version)
OLD REQUIREMENTS derived from it (answer-key style):
  (none)
NEW TEXT:
The approval of vehicles with regard to their Automatically Commanded Steering Functions (ACSF) or Risk Mitigation Function (RMF) which have been approved to UN Regulation No. 79, even when a system is exercising longitudinal control at the same time. However, if the manufacturer declares such ACSF or RMF to be part of DCAS, this UN Regulation applies irrespective of whether it has also been approved to UN Regulation No. 79.
OUR CURRENT FLAGS for this paragraph:
  (none)

=== PARAGRAPH 1.2.2 ===
OLD TEXT:
(paragraph did not exist in old version)
OLD REQUIREMENTS derived from it (answer-key style):
  (none)
NEW TEXT:
Vehicles of Categories X and Y [2] 2 As defined in the Consolidated Resolution on the Construction of Vehicles (R.E.3.), document ECE/TRANS/WP.29/78/Rev.8, para. 2 https://unece.org/transport/standards/transport/vehicle-regulations-wp29/resolutions 2. Definitions For the purposes of this Regulation: 2.1. _“Driver Control Assistance System (DCAS)”_ means the hardware and software collectively capable of assisting a driver in controlling the longitudinal and lateral motion of the vehicle on a sustained basis. Within this UN Regulation, DCAS is also referred to as “ _the system_ ”.
OUR CURRENT FLAGS for this paragraph:
  (none)

=== PARAGRAPH 2.21 ===
OLD TEXT:
“ _Rx Software Identification Number (RXSWIN)”_ means a dedicated identifier, defined by the vehicle manufacturer, representing information about the type approval relevant software of the Electronic Control System contributing to the UN Regulation No. 1XX type approval relevant characteristics of the vehicle.
OLD REQUIREMENTS derived from it (answer-key style):
  (none)
NEW TEXT:
“ _R_ _171_ _Software Identification Number (R_ _171_ _SWIN)”_ means a dedicated identifier, defined by the vehicle manufacturer, representing information about the type approval relevant software of the Electronic Control System contributing to the UN Regulation No. 171 type approval relevant characteristics of the vehicle.
OUR CURRENT FLAGS for this paragraph:
  (none)

=== PARAGRAPH 2.28 ===
OLD TEXT:
“ _Non-Highway_ ” means a type of road other than a highway as defined in paragraph 2.27.
OLD REQUIREMENTS derived from it (answer-key style):
  (none)
NEW TEXT:
“ _Non-Highway_ ” means a type of road other than a highway as defined in paragraph 2.27. 2.28.1. _“Highway-like road”_ means a section of non-highway on which all of the following characteristics are fulfilled for a reasonable distance: (a) Has at least two lanes in the direction the vehicles are driving; (b) Has a designated road speed limit of at least 80 km/h; (c) Pedestrians and cyclists are not prohibited (in contrast to a highway); (d) Is by design equipped with a physical separation that divides the traffic moving in the opposite direction; (e) Does not have at-grade (i.e. on the same level) marked pedestrian crossings, rail crossings, or road intersections. In this respect “designated road speed limit” is the speed limit which applies to a given section of road under normal circumstances, without taking into account temporary changes to this limit (e.g. due to roadworks, electronic variable limits, time of day variations, weather variations, etc.).
OUR CURRENT FLAGS for this paragraph:
  (none)

=== PARAGRAPH 5.2 ===
OLD TEXT:
DCAS interaction with other vehicle assistance systems
OLD REQUIREMENTS derived from it (answer-key style):
  (none)
NEW TEXT:
DCAS interaction with other vehicle assistance systems and ADS
OUR CURRENT FLAGS for this paragraph:
  (none)

=== PARAGRAPH 5.2.3 ===
OLD TEXT:
(paragraph did not exist in old version)
OLD REQUIREMENTS derived from it (answer-key style):
  (none)
NEW TEXT:
DCAS shall be switched to 'OFF' mode upon activation of an ADS feature, and shall not be able to be switched to 'ON' mode whilst an ADS feature is active.
OUR CURRENT FLAGS for this paragraph:
  added : DCAS shall be switched to 'OFF' mode upon activation of an ADS feature.
  added : DCAS shall not be able to be switched to 'ON' mode whilst an ADS feature is active.

=== PARAGRAPH 5.3.5.1 ===
OLD TEXT:
The system shall aim to detect the applicable system boundaries when DCAS or a feature of DCAS is in ‘on’ mode. If the system identifies that the system or feature boundary is exceeded, it shall transition into ‘standby’ mode and immediately notify the driver in accordance to the strategies described by the manufacturer as outlined in paragraph 5.3.5.2. and according to the HMI requirements defined in paragraph 5.5.4.1. The system shall terminate assistance to the driver provided by the affected feature or the system in a controllable way. The assistance termination strategy shall be described by the vehicle manufacturer and assessed according to Annex 3.
OLD REQUIREMENTS derived from it (answer-key style):
  R-012: While DCAS or a feature of DCAS is in ‘on’ mode, the DCAS shall aim to detect the applicable system boundaries.
  R-013: If the DCAS identifies that the system or feature boundary is exceeded, then the DCAS shall transition into ‘stand-by’ mode.
  R-014: If the DCAS identifies that the system or feature boundary is exceeded, then the DCAS shall immediately notify the driver in accordance to the strategies described by the manufacturer as outlined in paragraph 5.3.5.2. and according to the HMI requirements defined in paragraph 5.5.4.1.
  R-015: If the DCAS identifies that the system or feature boundary is exceeded, then the DCAS shall terminate assistance to the driver provided by the affected feature or the system in a controllable way.
  R-016: The assistance termination strategy for when the DCAS identifies that the system or feature boundary is exceeded shall be described by the vehicle manufacturer and assessed according to Annex 3.
NEW TEXT:
The system shall aim to detect the applicable system boundaries when DCAS or a feature of DCAS is in ‘on’ mode. If the system identifies that the system or feature boundary is exceeded, the system or the applicable feature shall leave the ‘active’ mode, with the exception of the driver unavailability response, and immediately notify the driver in accordance to the strategies described by the manufacturer as outlined in paragraph 5.3.5.2. and according to the HMI requirements defined in paragraph 5.5.4.1. If the driver is detected to be disengaged while the system or feature boundary is detected to be exceeded, the system shall continue providing lateral and longitudinal assistance to the extent possible or terminate assistance gradually in a controllable way, as outlined in the safety concept of the vehicle manufacturer. The driver state monitoring system shall continue to monitor driver disengagement until the driver is motorically and visually reengaged. The system shall initiate a driver unavailability response at the latest 10 seconds after it has detected to be beyond a system boundary, if the driver remains disengaged. The system shall terminate assistance to the driver provided by the affected feature or the system in a controllable way. The assistance termination strategy shall be described by the vehicle manufacturer and assessed according to Annex 3.
OUR CURRENT FLAGS for this paragraph:
  modified R-013: If the DCAS identifies that the system or feature boundary is exceeded, then the DCAS or the applicable feature shall leave the ‘active’ mode, with the exception of the driver unavailability response.
  added : If the driver is detected to be disengaged while the system or feature boundary is detected to be exceeded, the DCAS shall continue providing lateral and longitudinal assistance to the extent possible or terminate assist
  added : If the driver is detected to be disengaged while the system or feature boundary is detected to be exceeded, the driver state monitoring system shall continue to monitor driver disengagement until the driver is motoricall
  added : If the driver remains disengaged, the DCAS shall initiate a driver unavailability response at the latest 10 seconds after the DCAS has detected to be beyond a system boundary.
  modified R-014: If the DCAS identifies that the system or feature boundary is exceeded, then the DCAS or the applicable feature shall immediately notify the driver in accordance to the strategies described by the manufacturer as outline

=== PARAGRAPH 5.3.6.1.2 ===
OLD TEXT:
(paragraph did not exist in old version)
OLD REQUIREMENTS derived from it (answer-key style):
  (none)
NEW TEXT:
If a DCA is given while performing a system-initiated manoeuvre, the manufacturer shall consider the time required for the driver to direct their gaze to appropriate driving task relevant area(s) after the DCA is given in order to control the vehicle in the current situation when responding to this DCA. If the DCA is given whilst withholding HORs, this time shall be considered in addition to the time required by paragraph 5.3.6.1.1. The manufacturer shall explain to the Type Approval Authority the strategies and the timing with which the assistance is to be provided to the driver until the DCA is confirmed.
OUR CURRENT FLAGS for this paragraph:
  added : If a DCA is given while performing a system-initiated manoeuvre, the manufacturer shall consider the time required for the driver to direct their gaze to appropriate driving task relevant area(s) after the DCA is given i
  added : If the DCA is given during a system-initiated manoeuvre whilst withholding HORs, the time required for the driver to direct their gaze to appropriate driving task relevant area(s) shall be considered in addition to the t
  added : The manufacturer shall explain to the Type Approval Authority the strategies and the timing with which the assistance is to be provided to the driver until the DCA is confirmed.
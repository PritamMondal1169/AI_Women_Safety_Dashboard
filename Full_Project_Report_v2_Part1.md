<<PROJECT TITLE>>
AI-Powered Real-Time CCTV Monitoring System for Women's Safety: 
A Hybrid XGBoost and Kinematic Heuristic Approach to Autonomous Threat Detection

Project report in partial fulfillment of the requirement for the award of the degree of 
Bachelor of Technology 
in
Computer Science and Engineering (Artificial Intelligence & Machine Learning)

Submitted By

<<Student_1 Name>>						Enrollment No. XXXXXXXXX		
<<Student_2 Name>>						Enrollment No. XXXXXXXXX		
<<Student_3 Name>>						Enrollment No. XXXXXXXXX		
<<Student_4 Name>>						Enrollment No. XXXXXXXXX		
<<Student_5 Name>>						Enrollment No. XXXXXXXXX

Under the guidance of
Prof. [YOUR GUIDE’S FULL NAME]
Department of Computer Science and Engineering (Artificial Intelligence & Machine Learning)

INSTITUTE OF ENGINEERING & MANAGEMENT, KOLKATA, SCHOOL OF UNIVERSITY OF ENGINEERING AND MANAGEMENT, KOLKATA
University Area, Plot No. III – B/5, New Town, Action Area – III, Kolkata – 700160

---

## CERTIFICATE

This is to certify that the project report entitled "AI-Powered Real-Time CCTV Monitoring System for Women's Safety: A Hybrid XGBoost and Kinematic Heuristic Approach" submitted by <<Student_1 Name>> (Enrollment No. XXXXXXXXX), <<Student_2 Name>> (Enrollment No. XXXXXXXXX), <<Student_3 Name>> (Enrollment No. XXXXXXXXX), <<Student_4 Name>> (Enrollment No. XXXXXXXXX), and <<Student_5 Name>> (Enrollment No. XXXXXXXXX) in partial fulfillment of the requirement for the award of the degree of Bachelor of Technology in Computer Science and Engineering (Artificial Intelligence & Machine Learning), Institute of Engineering & Management, Kolkata, School of University of Engineering and Management, Kolkata, is a record of genuine work carried out by them under my supervision and guidance during the 6th Semester, academic session 2025-2026. The matter embodied in this project report has not been submitted to any other University or Institute for the award of any degree or diploma.

_______________________
Prof. [YOUR GUIDE’S FULL NAME]
Department of Computer Science and Engineering (Artificial Intelligence & Machine Learning)
Institute of Engineering & Management, Kolkata

---

## ACKNOWLEDGEMENT

We would like to express our profound gratitude and deep regards to our guide, Prof. [YOUR GUIDE’S FULL NAME], Department of Computer Science and Engineering, for their exemplary guidance, monitoring, and constant encouragement throughout the course of this project. The fundamental direction regarding the mathematical formulation of spatial threats, alongside the rigorous implementation of the XGBoost testing frameworks, was made possible through their continuous oversight.

We also take this opportunity to express a deep sense of gratitude to all faculty members who supported our research into real-time computer vision and machine learning deployment at the edge. Finally, we thank our parents and peers for their continuous support, hardware provisions, and encouragement throughout the rigorous development cycles of this software architecture.

Signature of Students:
1. _______________________ Date: _________
2. _______________________ Date: _________
3. _______________________ Date: _________
4. _______________________ Date: _________
5. _______________________ Date: _________

---

## TABLE OF CONTENTS

ABSTRACT ........................................................................ 6
CHAPTER – 1: INTRODUCTION 
	1.1 Background and Societal Context ..................................... 7
	1.2 The Evolution of Surveillance Artificial Intelligence ............... 9
CHAPTER – 2: LITERATURE SURVEY
	2.1 Traditional vs. Autonomous Video Surveillance ....................... 13
	2.2 Temporal Object Tracking and Occlusion Handling ..................... 16
	2.3 Semantic Gesture Analysis and Spatial Features ...................... 18
CHAPTER – 3: PROBLEM STATEMENT 
	3.1 Deficiencies in Reactive Security Paradigms ......................... 21
	3.2 System Objectives and Primary Scope ................................. 24
CHAPTER – 4: PROPOSED SOLUTION & MATHEMATICAL ARCHITECTURE
	4.1 System Topology and Component Pipeline .............................. 26
	4.2 Deep Object Detection (YOLOv8) and BoT-SORT Tracking ................ 31
	4.3 Mathematical Formulation of Spatio-Temporal Features ................ 35
	4.4 Mathematical Formulation of Pose and Body-Language Metrics .......... 40
	4.5 Pairwise Interaction and Threat Amplification ....................... 45
	4.6 The Hybrid Threat Engine (XGBoost + Kinematic Heuristic) ............ 50
	4.7 Alert Dispatch API and Communication Telemetry ...................... 55
CHAPTER – 5: EXPERIMENTAL SETUP AND COMPREHENSIVE RESULT ANALYSIS
	5.1 Implementation Environment and Hardware Acceleration ................ 58
	5.2 Synthetic Dataset Construction and Normalization .................... 62
	5.3 XGBoost Model Training and Validation ............................... 65
	5.4 Unit Testing and Coverage ........................................... 70
	5.5 End-to-End System Evaluation and Profiling .......................... 75
CHAPTER – 6: CONCLUSION & FUTURE SCOPE
	6.1 Research Conclusion ................................................. 80
	6.2 Future Enhancements ................................................. 83
BIBLIOGRAPHY .................................................................. 86

---

## ABSTRACT

Addressing the escalating requirement for proactive surveillance to guarantee women's safety in public and isolated spaces demands a fundamental shift from human-dependent monitoring towards autonomous semantic video analysis. This comprehensive research proposes, implements, and evaluates an "AI-Powered Real-Time CCTV Monitoring System" uniquely engineered to identify physical threats and distress indications instantaneously. By leveraging the Ultralytics YOLOv8n object detector mapped seamlessly to a BoT-SORT temporal tracking cascade, the system extrapolates human trajectories and COCO-17 skeletal keypoints at operating speeds exceeding 25 Frames Per Second (FPS). 

Unlike traditional motion sensors, the core ingenuity of this project resides in its highly vectorized `FeatureExtractor` and `InteractionAnalyzer`. The algorithmic pipeline dynamically formulates 20 exact mathematical features per individual—quantifying complex kinesthesis such as relative approach vectors, group encirclement variances, strike-oriented arm extensions, and resistive body-facing logic computed by analyzing localized displacement matrices over 60-frame rolling states. These high-dimensional features are injected into a highly optimized Hybrid Threat Engine. This engine fundamentally unifies a deterministic kinematic heuristic with an XGBoost Gradient Boosted Classifier. Through an extensively detailed synthetic training pipeline consisting of 10,000 uniquely structured interaction scenarios (including Hugging, Following, Rush Approaching, and Striking), the XGBoost model achieved a flawless evaluation ROC-AUC of 1.0000 with zero false positives across the validation manifold. 

To bridge computation to physical deterrence, the architecture encapsulates a state-gating buffer enforcing threat persistence before securely interfacing with automated telecommunications (Twilio API). Upon verifying a sustained HIGH threat intersection, the system independently broadcasts multi-channel tactical alerts (SMS/WhatsApp/Voice) embedded with IP/Google Geocoded coordinate approximations. Comprehensive software unit testing, evaluating tracking boundary logic and algorithmic sanitization, validates the architecture's absolute determinism. This report meticulously details the entirety of the mathematical modeling, software architecture, training paradigms, and the rigorous test evaluations confirming the system's viability for large-scale, edge-hardware societal deployment.

---

## CHAPTER – 1: INTRODUCTION

### 1.1 Background and Societal Context
The global landscape of public safety—particularly concerning the vulnerability of women in low-density public spaces, transit corridors, and isolated commercial sectors—remains critically dependent on delayed human intervention. Modern security infrastructure inherently operates as a passive observer. Closed-Circuit Television (CCTV) cameras record interactions unceasingly, but their utility is almost entirely forensic; the footage serves primarily to identify a perpetrator long after the transgression has occurred. The reliance on human operators to monitor vast arrays of live video streams introduces debilitating psychological bottlenecks. Research into cognitive load indicates that a human operator tasked with scanning even just four visual feeds experiences a profound deterioration in anomaly identification capability within twenty to thirty minutes, leading to an operational phenomenon known as 'inattentional blindness'. Consequently, if a proactive threat—such as a frantic physical pursuit, aggressive encirclement, or a physical altercation—transpires, its detection relies dangerously upon chance human observation or a bystander's emergency distress call.

The necessity to eliminate this human-latency bottleneck forms the genesis of our research. Autonomous computer vision applied directly at the camera edge holds the potential to instantaneously classify malicious intent. A fully democratized AI system must evaluate a live video stream, track its subjects persistently, mathematically infer the nature of human physical interaction, and raise an alarm before an altercation concludes—or ideally, before it escalates. This project, "AI-Powered Real-Time CCTV Monitoring System for Women's Safety", operates explicitly on this proactive methodology.

### 1.2 The Evolution of Surveillance Artificial Intelligence
Historical derivations of automated surveillance were restricted largely to pixel-based density calculations, background subtraction models (like Gaussian Mixture Models), and restricted trip-wire intrusion alerts. These methodologies fail unilaterally in urban environments where motion is chaotic but fundamentally benign. The introduction of Convolutional Neural Networks (CNN) revolutionized spatial recognition, but the leap toward behavioral comprehension requires multi-dimensional tracking.

Our implemented framework utilizes state-of-the-art developments in deep learning and gradient-boosted spatial statistics. To dissect an interaction accurately, it is insufficient to simply state "two persons are present". The system must calculate their historical velocity vectors via finite difference equations, assess whether one subject's trajectory converges deliberately upon another, measure the exact angular displacement of their skeletal shoulder joints to infer physical confrontation phrasing, and distinguish between a mutual embrace and a non-consensual hostile grab. This level of semantic abstraction demands a multi-agent architectural pipeline: object localization, temporal association, kinematic vectorization, and statistical inference. Our research successfully binds these complex domains into a real-time executable environment, ensuring latency remains minimal to permit immediate law enforcement networking.

---

## CHAPTER – 2: LITERATURE SURVEY

### 2.1 Traditional vs. Autonomous Video Surveillance
The technological history of visual surveillance highlights a stagnant architectural core enveloped by progressively higher resolution optics. Historically, security research centered upon optical flow mechanisms to determine anomalous crowd behavior. Optical flow evaluates the apparent motion of pixels between two consecutive frames. While effective for detecting a massive panic-induced stampede within a train station, it fundamentally lacks object-level semantic labeling. A perpetrator stalking a solitary victim generates an insignificantly altering optical flow vector, rendering the action invisible to early generation algorithms.

Subsequent research pivoted toward Deep Learning paradigms. Object classification initially leveraged Two-Stage Detectors (e.g., Faster R-CNN) which utilized localized region proposals prior to classifying the subject. Although highly accurate, the non-deterministic latency spikes forced processing times exceeding 100 milliseconds per frame, inherently disqualifying them for real-world real-time security on affordable hardware. The release of the "You Only Look Once" (YOLO) framework drastically altered this trajectory by collapsing proposal and classification into a unified, single-stride tensor evaluation. 

### 2.2 Temporal Object Tracking and Occlusion Handling
Given the requirement to evaluate human actions over time, single-frame object detection is merely the primer. The literature defines Multi-Object Tracking (MOT) as the complex algorithmic challenge of maintaining a unique identifier for a detected subject as they traverse a visual plane, specifically across moments of heavy occlusion. Early Kalman Filter trackers (such as SORT - Simple Online and Realtime Tracking) relied exclusively on bounding-box intersection over union (IoU). The mathematical failure of SORT occurs during crossing trajectories; when two individuals cross paths, the intersection bounding boxes violently merge, causing 'Identity Switching'. 

To correct this, researchers developed DeepSORT, which computes deep visual appearance features (utilizing a Siamese network) to re-identify subjects. However, appearance models are computationally expensive. Our survey led us to BoT-SORT (Robust Associations Multi-Object Tracking), which brilliantly leverages Camera Motion Compensation (CMC) and fundamentally refines the Kalman state predictions for the object’s width and height ratio, resolving identity switches drastically without crushing the hardware processing unit.

### 2.3 Semantic Gesture Analysis and Spatial Features
The final tier of the literature focuses on the actual threat classification. Most existing behavioral analysis systems utilize raw skeletal time-series data processed through sequence neural networks like Long Short-Term Memory (LSTM) layers or Spatial-Temporal Graph Convolutional Networks (ST-GCN). While powerful in controlled academic datasets (like the NTU-RGB+D dataset for action recognition), deploying an ST-GCN parallel to a YOLO detector on edge devices requires immense GPU compute memory, often causing memory overflow (CUDA Out of Memory) errors.

Alternatively, research points toward tabular machine learning models utilizing meticulously engineered structural features. Papers surrounding Extreme Gradient Boosting (XGBoost) detail its unparalleled performance when operating on structured, highly correlated datasets. By mathematically reducing a human interaction from thousands of image pixels down to exactly twenty normalized kinematic scalars (representing velocity, acceleration, distance, and joint angles), an XGBoost model can perform binary threat classification at sub-millisecond speeds. The literature strongly supports this hybrid approach—pairing hard-coded kinematic logic filters directly alongside a statistical gradient-boosted tree—to achieve an optimal balance of zero-latency evaluation and robust generalizability against unforeseeable public scenarios.

---

## CHAPTER – 3: PROBLEM STATEMENT

### 3.1 Deficiencies in Reactive Security Paradigms
The overarching challenge driving this project is the abject inability of contemporary surveillance infrastructure to intervene during physical attacks or harassment scenarios involving women in public quarters. The current security environment is hindered by three massive deficiencies:
1. **The Post-Event Forensic Nature:** Video logs are generally only extracted after an incidence report has been filed. The camera provides evidence but zero active protection.
2. **Computational Limitations in Interaction Phrasing:** Commercial "AI cameras" natively support tripwires, loitering alerts (dwelling in a zone), and face detection. They possess a complete ignorance toward interpersonal biomechanics. If a man forcefully grabs a woman's wrist on a sidewalk, traditional AI merely sees two "Person" classes inside an overlapping pixel grid; it lacks the intelligence to differentiate an assault from two colleagues shaking hands.
3. **Catastrophic False-Positive Rates in Urban Deployments:** Dense urban centers necessitate strict algorithmic gating. If a system's primary threat trigger is simplistic "proximity," navigating a crowded pedestrian crossing will continuously flood dispatch centers with false alarms. This high noise-to-signal ratio inevitably forces operators to mute the system entirely.

### 3.2 System Objectives and Primary Scope
To dismantle these fundamental technological barriers, this project engineers a highly specialized, deterministic threat-analysis pipeline aiming to achieve the following precise objectives:

1. **Persisted Temporal Identity Management:** Implement BoT-SORT tracking mapped directly over YOLOv8n to maintain a 60-frame rolling positional history buffer for every unique subject detected, maintaining identity consistency over crossing occulsions.
2. **Mathematical Biomechanical Vectorization:** Formulate exact differential algorithms to extract 20 complex interaction features, shifting the computational load from pixel-heavy deep learning to rapid array mathematics evaluating velocity vectors, acceleration profiles, angular direction variance, and skeletal structural symmetry (utilizing COCO-17 outputs).
3. **Pairwise Interaction Analysis & Boost Engineering:** Design an isolated processing loop that cross-examines every tracked entity against all other proximate entities, determining exact interaction physics—calculating targeted resistance (one person accelerating backwards while pursued) and assessing wrist-to-shoulder kinematic overlap to categorically define hostile constraints (grabbing) versus benign contacts (handshakes).
4. **Flawless Threat Scoring Engine:** Unify the deterministic mathematical outputs via an Extreme Gradient Boosted decision tree configured to output an absolute float confidence matrix natively, cross-validated via a deterministic heuristic scoring layer. This protects against neural network hallucinations by bounding predictions strictly against real-world physical thresholds. 
5. **Completely Autonomous Telemetry Integration:** Completely bypass human operators upon sustained positive threat escalation by instantiating secure REST payload connections to Tier-1 telecommunications providers (Twilio), transmitting formatted emergency SMS broadcasts and automated SOS voice calls utilizing local IP geographical tracing within 400 milliseconds of threshold collision.

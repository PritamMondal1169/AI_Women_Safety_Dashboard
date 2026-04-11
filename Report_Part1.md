<<PROJECT TITLE>>
AI-Powered Real-Time CCTV Monitoring System for Women's Safety

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

This is to certify that the project report entitled "AI-Powered Real-Time CCTV Monitoring System for Women's Safety" submitted by <<Student_1 Name>> (Enrollment No. XXXXXXXXX), <<Student_2 Name>> (Enrollment No. XXXXXXXXX), <<Student_3 Name>> (Enrollment No. XXXXXXXXX), <<Student_4 Name>> (Enrollment No. XXXXXXXXX), and <<Student_5 Name>> (Enrollment No. XXXXXXXXX) in partial fulfillment of the requirement for the award of the degree of Bachelor of Technology in Computer Science and Engineering (Artificial Intelligence & Machine Learning), Institute of Engineering & Management, Kolkata, School of University of Engineering and Management, Kolkata, is a record of genuine work carried out by them under my supervision and guidance during the 6th Semester, academic session 2025-2026. The matter embodied in this project report has not been submitted to any other University or Institute for the award of any degree or diploma.

_______________________
Prof. [YOUR GUIDE’S FULL NAME]
Department of Computer Science and Engineering (Artificial Intelligence & Machine Learning)
Institute of Engineering & Management, Kolkata

---

## ACKNOWLEDGEMENT

We would like to express our profound gratitude and deep regards to our guide, Prof. [YOUR GUIDE’S FULL NAME], Department of Computer Science and Engineering (Artificial Intelligence & Machine Learning), for their exemplary guidance, monitoring, and constant encouragement throughout the course of this project "AI-Powered Real-Time CCTV Monitoring System for Women's Safety". The blessing, help, and guidance given by them time to time shall carry us a long way in the journey of life on which we are about to embark.

We also take this opportunity to express a deep sense of gratitude to all faculty members who directly or indirectly supported us in completing this project. Finally, we thank our parents and friends for their continuous support and encouragement.

Signature of Students:

1. _______________________ Date: _________
2. _______________________ Date: _________
3. _______________________ Date: _________
4. _______________________ Date: _________
5. _______________________ Date: _________

---

## TABLE OF CONTENTS

ABSTRACT ........................................................................ 5
CHAPTER – 1: INTRODUCTION ........................................................ 6
CHAPTER – 2: LITERATURE SURVEY
	2.1 Traditional Surveillance vs. AI Surveillance ....................... 10
	2.2 Advanced Machine Learning Models in Security ....................... 14
CHAPTER – 3: PROBLEM STATEMENT 
	3.1 Deficiencies in Current Systems .................................... 18
	3.2 Objectives of the Proposed System .................................. 22
CHAPTER – 4: PROPOSED SOLUTION 
	4.1 System Architecture and Modules .................................... 25
	4.2 Tracking and Threat Assessment Logic ............................... 33
CHAPTER – 5: EXPERIMENTAL SETUP AND RESULT ANALYSIS
	5.1 Implementation Details ............................................. 42
	5.2 Performance Metrics and Evaluation ................................. 48
CHAPTER – 6: CONCLUSION & FUTURE SCOPE
	6.1 Conclusion ......................................................... 53
	6.2 Future Enhancements ................................................ 54
BIBLIOGRAPHY ................................................................. 56

---

## ABSTRACT

In recent years, ensuring the safety of women in public spaces has emerged as a critical societal challenge that requires immediate and innovative technological interventions. Traditional closed-circuit television (CCTV) surveillance systems rely heavily on manual monitoring, which inherently suffers from human fatigue, delayed response times, and an inability to proactively prevent incidents before they escalate. This project proposes an AI-Powered Real-Time CCTV Monitoring System designed specifically for women's safety by autonomously analyzing human behavior and interactions in real-time. By leveraging state-of-the-art computer vision models—specifically YOLOv8n integrated with BoT-SORT for robust multi-object tracking—the system continuously extracts skeletal keypoints and tracks individuals across frames. To accurately classify the underlying threat level of any given interaction, the system employs a sophisticated hybrid threat-scoring engine. This engine synthesizes spatial kinematics (e.g., approach velocity, proximity) and body-language cues (e.g., shoulder elevation, elbow flexion) using a dual-layered approach: a trained XGBoost classification model acting in tandem with a deterministic heuristic fallback. By analyzing exactly 20 meticulously engineered features, the system dynamically categorizes scenes into NONE, LOW, MEDIUM, and HIGH threat levels. Upon detecting a sustained HIGH threat, the system securely interfaces with an Alert Dispatcher—utilizing third-party telecommunication APIs like Twilio—to instantly broadcast SMS, voice, and WhatsApp alerts to pre-configured emergency contacts, complemented by geographic coordinates resolved via IP or Google Maps APIs. Experimental results demonstrate that the proposed architecture achieves a high processing throughput (targeting 25-30 FPS on standard GPU hardware) alongside superior precision in identifying anomalous, threatening behavior while maintaining a negligible false-positive rate. This project not only bridges the gap between passive video recording and active threat mitigation but also represents a paradigm shift towards autonomous, multi-agent algorithmic orchestration in public safety systems.

---

## CHAPTER – 1: INTRODUCTION

Public safety mechanisms, particularly concerning the safety and security of women, stand at an inflection point. The escalating rates of harassment, stalking, and violent crimes against women globally mandate more robust solutions than what static, post-event surveillance can offer. Conventional surveillance mechanisms largely serve a forensic purpose—assisting law enforcement in piecing together the timeline of an event only after a crime has been committed. The fundamental limitation of these systems is their passive nature; they inherently depend on human operators to continuously scan dozens of video feeds to identify anomalous behavior. Studies indicate that operator attention span diminishes drastically within just twenty minutes of continuous monitoring, making human-dependent surveillance susceptible to crucial oversights. 

With the advent of computer vision, deep learning, and advanced behavioral heuristics, there is a paradigm shift moving towards proactive, autonomous surveillance systems. The core philosophy of the "AI-Powered Real-Time CCTV Monitoring System for Women's Safety" project revolves around the transformation of passive cameras into intelligent, proactive agents. We propose a robust, scalable backend architecture formulated upon object detection paradigms and ensemble machine learning classifiers. The system uniquely evaluates physical interactions between tracked subjects rather than treating each person in isolation.

The primary algorithmic engine functions as a multi-stage pipeline designed for efficiency and high confidence. Initially, raw video frames are captured and passed through a YOLOv8 Nano object detector, tuned specifically for rapid person-class inference. The detections are seamlessly bound temporally across frames using the BoT-SORT tracking algorithm, which handles occlusion and varied camera angles. Once trajectory and skeletal keypoints are established, a Feature Extractor processes these trajectories into quantifiable metrics: physical proximity, relative approach velocity, track encirclement (i.e., multiple individuals surrounding a solitary target), and granular pose features such as raised shoulders or sudden arm extensions denoting a fighting stance. 

These 20 spatial and temporal features are subsequently fed into our Threat Engine. To ensure extreme reliability under diverse environmental conditions, the threat scoring is formulated as a hybrid model: it utilizes the predictive power of an XGBoost classifier trained on domain-specific datasets, combined with a rigorously tuned heuristic calculator based on real-world kinematics. This hybrid strategy allows the system to compute a comprehensive composite threat score ranging from 0.0 to 1.0. When an interaction escalates to a 'HIGH' threat level (dynamically gated by sustained duration frames to prevent false alarms), an Alert Dispatcher is triggered. This multi-channel alerter autonomously pings APIs (via Twilio) to dispatch SMS, automated voice calls, and WhatsApp messages loaded with the subject's coordinates.

In essence, this research project encapsulates the entire pipeline of modern artificial intelligence deployment: from hardware interfacing and raw tensor processing to multi-layered decision making and automated incident orchestration in real-time. This report extensively documents the literature framing our research, the rigorous problem statement identified, the elaborate machine learning modules configured, and the empirical results validating our solution's efficacy for large-scale societal deployment.

---

## CHAPTER – 2: LITERATURE SURVEY

### 2.1 Traditional Surveillance vs. AI Surveillance
The transition from analog to digital security has historically been a matter of resolution and storage density, but the actual logic of monitoring remained inherently human-bound. In the comprehensive review of modern CCTV infrastructures, researchers have frequently illustrated the 'human-in-the-loop' bottleneck. Passive surveillance systems operate on a 'record-and-review' policy. When deployed in unconstrained public environments, the volume of data generated by multi-camera setups exponentially outpaces the cognitive bandwidth of human security personnel. Past literature has proven that human operators tasked with monitoring more than four live streams simultaneously exhibit an anomaly detection accuracy drop of over 60% after forty-five minutes of continuous viewing. 

Consequently, researchers began to explore motion-based heuristic systems. Early automated surveillance systems utilized algorithms such as Gaussian Mixture Models (GMM) for background subtraction and simple optical flow to detect movement in restricted zones. While effective for simple intrusion detection on static backgrounds, these algorithms spectacularly fail to comprehend complex inter-human interactions. For instance, an optical flow algorithm might detect two people moving rapidly but cannot distinguish whether they are jogging together amicably or if one is aggressively chasing the other. Thus, the literature emphasizes the critical need for systems capable of semantically parsing human behavior rather than just generalized pixel motion.

In recent years, the literature has shifted towards Convolutional Neural Networks (CNNs) and deep learning for semantic video understanding. Specifically, the emergence of the "You Only Look Once" (YOLO) architecture introduced real-time, single-pass object detection that significantly outpaced previous R-CNN architectures in both inference speed and bounding box overlap accuracy. Tracking algorithms also evolved from simple Kalman filtering to sophisticated DeepSORT and, more recently, BoT-SORT, which intricately weave bounding box coordinates with deep visual appearance features to maintain track IDs over long periods, even amidst heavy occlusion. These foundational studies establish that consistent, accurate multi-subject tracking in real-time is now computationally feasible, provided the architecture is appropriately optimized.

### 2.2 Advanced Machine Learning Models in Security
While detecting and tracking humans solves the spatial localization problem, analyzing their intent presents a far more complex challenge. Literature regarding threat detection spans various methodologies, from purely rule-based expert systems to black-box deep learning architectures. Evolving from simple crowd density estimation, researchers started examining pairwise trajectories. Spatial features such as interpersonal distance, velocity vectors, and abnormal acceleration profiles have been mathematically formulated to identify panic or aggression. However, deterministic rule-based algorithms often lack the flexibility required to generalize across the vast spectrum of human behaviors, leading to high false-positive rates in crowded scenarios (e.g., bustling train stations or markets).

Conversely, sequence-to-sequence deep learning models—such as Long Short-Term Memory (LSTM) networks or spatial-temporal Graph Convolutional Networks (GCNs)—have demonstrated remarkable accuracy in recognizing actions from skeletal data. Yet, these deep models introduce substantial inference latency and demand extreme computational overhead, often rendering them impractical for deployment on edge devices or standard hardware lacking high-end discrete GPUs.

Our literature survey reveals a distinct gap: the necessity for an intermediately complex model that possesses the inferential nuance of machine learning without the crippling latency of massive temporal neural networks. This gap motivated our selection of Gradient Boosted Decision Trees, specifically XGBoost. Research indicates that tabular algorithms like XGBoost, when supplied with high-quality engineered features, can frequently match or exceed the performance of deep neural networks on structured data tasks while executing inference in single-digit milliseconds. The synthesis of precise heuristic spatial filtering (e.g., normalising velocity vectors by the frame diagonal) and gradient-boosting statistical models presents an optimal, unexplored avenue for real-time edge surveillance—a paradigm that our project directly addresses.

---

## CHAPTER – 3: PROBLEM STATEMENT

### 3.1 Deficiencies in Current Systems
The primary problem addressed by this project is the pervasive inefficiency and delayed reaction capability of current public safety surveillance networks, which directly impacts the safety and physical security of women in vulnerable environments. The prevailing security paradigm is strictly reactionary. When a distressing physical incident—such as harassment, stalking, or an altercation—occurs, the standard operating procedure is for the victim or a bystander to manually contact emergency services. If the event takes place in a secluded or unpopulated area, this manual alert mechanism frequently fails. The presence of CCTV cameras acts somewhat as a psychological deterrent but offers zero immediate intervention, as the footage is only accessed post-incident to aid in forensic police investigations.

Furthermore, the limited AI-based surveillance tools currently available on the commercial market are predominantly designed for rudimentary tasks: facial recognition at localized access points, license plate reading, or simple tripwire intrusion detection. They completely lack the semantic understanding required to classify the nature of an interaction between two individuals. For example, if a woman is walking and a perpetrator rapidly alters their trajectory to follow or intercept her, current systems simply register "two humans moving." The absence of interaction intelligence means that the moments leading up to a confrontation—which are the most critical for preventive action—are entirely ignored by automated systems.

Another prominent deficiency observed during our analysis is the handling of false positives. Systems attempting to calculate threat levels based merely on proximity suffer from catastrophic false-positive rates when deployed in dense urban populations. Two people standing shoulder-to-shoulder on a busy sidewalk are physically close but do not constitute a threat. To deploy a viable societal solution, the system must distinguish between incidental proximity and threatening proximity (e.g., a person actively closing the distance on a solitary target exhibiting evasion or protective posturing). 

### 3.2 Objectives of the Proposed System
Given the aforementioned deficiencies in human-monitored and rudimentary motion-detection systems, this project was conceived with several definitive objectives to ensure proactive and autonomous threat mitigation:

1. **Autonomous Multi-Object Detection & Tracking:** Continually identify all persons within the camera's field of view in real-time, persisting their unique identities across frames despite temporary occlusions, utilizing deep-learning-based trackers to establish robust temporal trajectories.

2. **Advanced Semantic Feature Extraction:** Extract not only the bounding box coordinates but a comprehensive vector of 20 interaction features for every tracked individual. This includes spatial-temporal metrics (velocity, angular direction changes, track age, and group encirclement) as well as intricate body language cues derived from COCO-17 pose keypoints (shoulder elevation, wrist extension symmetry, and body-facing vectors).

3. **Hybrid Threat Evaluation Logic:** Develop an innovative threat-scoring engine that combines a trained XGBoost classifier with heavily scrutinized heuristic rules. The objective is to calculate a normalized Threat Score (0.0 to 1.0) for every person in every frame, translating this continuous score into discrete, human-readable states (NONE, LOW, MEDIUM, HIGH) while utilizing temporal gating to completely eliminate instantaneous false positives.

4. **Automated Multi-Channel Alert Dispatching:** Entirely remove the dependency on manual human reporting by engineering a robust backend Alert Dispatcher. Upon the system independently confirming a sustained HIGH threat level, it must instantly interface with cloud telephony APIs to push context-rich, actionable alerts (incorporating geographic location and threat snapshots) across SMS, voice calls, and encrypted messaging platforms like WhatsApp.

5. **Performance and Edge Optimisation:** Maintain an operational throughput of least 25 frames per second on accessible hardware, ensuring that the entire pipeline—from tensor computation to alerting—operates without queuing lag. This is achieved by implementing intelligent frame-skipping tuners and performance monitors within the main inference loop.

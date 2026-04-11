## CHAPTER – 4: PROPOSED SOLUTION & MATHEMATICAL ARCHITECTURE

The architectural framework of the proposed AI Surveillance System inherently bypasses simplistic pixel-motion logic. We implement a deeply federated, five-stage multi-threaded software pipe architecture operating at the network edge: Video Ingestion, Deep Tracking, Biomechanical Vectorization, Pairwise Interaction Analysis, and XGBoost/Heuristic Evaluation.

### 4.1 System Topology and Component Pipeline
At runtime, high-definition matrices enter the OpenCV reader node (`cv2.VideoCapture`). To insulate the inference engine from potential camera buffering desynchronization, the application utilizes asynchronous multiprocessing. The uncompressed frame tensor is scaled dynamically (default `[640x640]`) and funneled directly into the GPU pipeline via PyTorch tensors (`cuda:0`). Every component class operates modularly; `main.py` simply coordinates the message passing between the `Detector`, the temporal `TrackManager`, the geometric `FeatureExtractor`, the structural `InteractionAnalyzer`, and ultimately the `ThreatEngine` array. If an alert condition hits the HIGH threshold for an established number of rolling frames, the `AlertDispatcher` encapsulates the exact timestamped data point and pushes it externally over HTTP protocols.

### 4.2 Deep Object Detection (YOLOv8) and BoT-SORT Tracking
The `Detector` class mounts the Ultralytics YOLOv8n-pose backend tensor. Crucially, the system executes inference strictly on `class 0` (Person). A forward pass yields bounding box coordinates alongside an array containing 17 Cartesian points $P = \{(x_i, y_i, conf_i)\}_{i=1}^{17}$ representing joints (shoulders, elbows, wrists, hips). Filtering removes detections where bounding area $< 500$ squared pixels or overall confidence drops beneath $0.55$.
Because threats are inherently temporal (taking place over a span of time), instantaneous bounding boxes are insufficient. The backend integrates BoT-SORT to map bounding boxes between frames $t$ and $t-1$. When a new bounding detection coordinates successfully resolve via Intersection-over-Union mapping or motion-prediction Kalman filtering against an established Tracker ID, the memory repository inside the `TrackManager` pushes the new geometry into a 60-slot rolling deque containing positional matrices, preventing memory leaks over extended monitoring durations. Tracks missing beyond 45 consecutive frames are definitively reaped by the garbage collector.

### 4.3 Mathematical Formulation of Spatio-Temporal Features
Every tracked individual is cross-evaluated against their local neighborhood by the `FeatureExtractor`, transposing a bounding box trail into a continuous feature vector of 20 normalized elements ($[0,1]$ space) required by the statistical tree.

**1. Euclidean Proximity & Normalization:**
Distance between Target $(x_t, y_t)$ and Neighbor $(x_n, y_n)$ is strictly calculated via the Euclidean norm:
$$d = \sqrt{(x_t - x_n)^2 + (y_t - y_n)^2}$$
Normalized against the total camera frame diagonal ($D = \sqrt{W^2 + H^2}$), proximity becomes heavily scaled within the 5% threshold:
$$P_{norm} = \text{clip}\left(\frac{d}{0.1 \times D}, 0.0, 1.0\right)$$

**2. Kinematic Speed:**
Utilizing the finite positions matrix $C = \{(x_k, y_k)\}_{k=t-N}^{t}$, speed is derived via positional differentiation spanning a $\Delta t$ epoch (generally $0.5$ seconds or 15 frames):
$$v_{px} = \frac{\|\vec{C_t} - \vec{C_{t-15}}\|}{\Delta t}$$
The scalar speed is then thresholded against human biological constants (e.g. running max velocity) scaled to the frame depth structure.

**3. Vector Acceleration and Erratic Approach Profile:**
Acceleration is purely the difference of sequential velocity vectors:
$$a = \frac{\|v_t - v_{t-1}\|}{\Delta t}$$
Tracking stalkers uniquely relies upon Erratic Angular Displacement. If sequential velocity vectors are $\vec{v}_1$ and $\vec{v}_2$, the directional change $\theta$ is extracted using the geometric dot product:
$$\theta = \arccos\left(\frac{\vec{v}_1 \cdot \vec{v}_2}{\|\vec{v}_1\| \cdot \|\vec{v}_2\|}\right)$$

**4. Group Encirclement & Isolation Logic:**
A defining characteristic of mob violence is encirclement. Using angular separation, we map all neighboring centers angularly around the target center. Let $\phi_1, \phi_2, ... \phi_m$ be sorted angles corresponding to the $m$ closest entities. The maximum angular gap $\Delta\phi_{max}$ determines the opening for the victim to escape. The Encirclement score is thus modeled exactly as:
$$E = \text{clip}\left(1.0 - \frac{\Delta\phi_{max}}{2\pi}, \, 0.0, \, 1.0\right)$$
A group of 4 subjects blocking N/S/E/W paths yields a theoretical gap nearing $\frac{\pi}{2}$, triggering a devastating $E > 0.75$ penalty.

### 4.4 Mathematical Formulation of Pose and Body-Language Metrics
The second spatial layer analyzes aggressive posturing abstracted from the 17 skeletal keypoints. A standard CNN only records people standing; our `PoseFeatureExtractor` calculates fighting stances.

**1. Arm Extension Targeting:**
Calculating the angular extension over three joints—Shoulder ($j_S$), Elbow ($j_E$), Wrist ($j_W$). A completely straightened arm yields 180 degrees.
$$\gamma = \arccos\left(\frac{ (\vec{j_E} - \vec{j_S}) \cdot (\vec{j_W} - \vec{j_E}) }{ \| \vec{j_E} - \vec{j_S} \| \cdot \| \vec{j_W} - \vec{j_E} \| } \right)$$

**2. Body Facing Confrontations:**
To distinguish parallel walking companions from face-to-face altercations, we establish a perpendicular plane across the left and right shoulders. The scalar directional dot product determines orientation; converging orientations reaching parallel configurations dictate face-to-face (congenial) or face-to-face (confrontational) depending heavily on sequential velocities.

### 4.5 Pairwise Interaction and Threat Amplification
Beyond individual analysis, the system introduces an intensive `InteractionAnalyzer`. A fundamental complication resolved by this engine is differentiating a violent collision (a mugging) from a passionate embrace (a group hug).

**1. The Mutual Arm Symmetry Theorem:**
Hugging requires mutual spatial investment. An assault rarely features symmetric limb extension. Leveraging the x-coordinates of the left and right wrists ($W_L, W_R$) and the shoulder midpoint ($M_X$), horizontal extensions are found:
$$L_{ext} = |W_{Lx} - M_X| \quad ; \quad R_{ext} = |W_{Rx} - M_X|$$
Symmetry is thus strictly evaluated as:
$$S = \min\left(1.0 - \frac{|L_{ext} - R_{ext}|}{\max(L_{ext}, R_{ext})}, \, 1.0\right)$$
Two individuals with high structural symmetry $S > 0.6$, minimal speed, and extreme wrist proximity inherently register as 'FRIENDLY' interaction, thereby triggering a mathematically inverted negative algorithmic Threat Boost ($-0.2$), protecting the system from generating false positives at crowded train stations.

**2. Physical Resistance Vectors:**
Should a target forcibly pull away (physical resistance thresholding), velocity vectors and unit direction components $\vec{d}_{12} = \frac{p_2 - p_1}{\|p_2 - p_1\|}$ are evaluated. If $\vec{v}_1 \cdot \vec{d}_{12} < -0.3$ (the target is accelerating away from the interaction anchor), resistance variables surge toward $1.0$, universally bypassing XGBoost confidence constraints to flag a `DANGER` status immediately (Threat amplified linearly by $+0.8 * MAX\_BOOST$).

### 4.6 The Hybrid Threat Engine (XGBoost + Kinematic Heuristic)
The composite pipeline funnels the aforementioned 20 features (normalized dimension $D=20$) along with interaction amplifications directly into the `ThreatEngine`. Since neural network topologies (LSTMs) perform poorly on discontinuous tabular dimensions, we leverage an Extreme Gradient Boosted ensemble of decision trees.

The XGBoost model, evaluated via logistical learning formulations, produces a float confidence probability $X_{score} \in [0,1]$. Simultaneously, a heavily bounded deterministic heuristic evaluates logic bands:
$$H_{score} = \text{Heuristic}(a, v, \theta, P_{norm}, E)$$
The heuristic specifically gates impossible realities: speed strictly operates as a multiplier uniquely when it aligns positively with velocity *towards* the target.

Finally, the hybrid engine merges inferences via blending constant $\alpha$:
$$\text{Threat}_{final} = \alpha \cdot X_{score} + (1 - \alpha) \cdot H_{score} + \text{Boost}_{\text{Pairwise}}$$
Where $\alpha$ permits software developers to seamlessly tilt trust between machine learning models versus rigid deterministic constraints depending on deployment environments.

**Sustained Contextual Gating:**
Instantaneous mathematical anomalies randomly occur in camera streams. We filter absolute false noise by enforcing state demotion algorithms. Tracking systems bin $Threat_{final}$ scores discretely (e.g. HIGH if $> 0.80$). Crucially, escalation is blocked until tracking counters document threshold collision continuously $N_{frames} > 15$. Demotion is instantaneous; therefore, only relentless, verified aggression trips external circuits.

### 4.7 Alert Dispatch API and Communication Telemetry
Bypassing local monitoring, the `AlertDispatcher` object initializes upon $Threat_{final} \ge 0.8$ breaking the sustained threshold frame barrier. Encrypted API endpoints instantiate secure HTTP requests directed toward Twilio Cloud Systems. The JSON payload encompasses real-world epoch timestamps, camera ID nodes, and estimated physical geolocation mappings (resolved via standard IP-to-Geo network hooks). Pre-defined hierarchical matrices determine delivery routing: the local enforcement node receives SMS directives populated with the `AlertEvent` object snapshot variables (Current Subject ID, Confidence Metrics), concurrently while automated voice synthesizers alert first responders precisely describing the nature of the detected spatial threat anomaly.

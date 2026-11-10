from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pathlib import Path

OUT = Path(__file__).parent
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
blank = prs.slide_layouts[6]
BG = RGBColor(248,250,252); NAVY = RGBColor(24,48,84); TEXT=RGBColor(39,54,72); MUTED=RGBColor(93,109,128)
BLUE=RGBColor(46,105,174); TEAL=RGBColor(35,135,139); ORANGE=RGBColor(222,124,35); PALE=RGBColor(232,240,248)
LINE=RGBColor(211,221,231); WHITE=RGBColor(255,255,255); GREEN=RGBColor(44,126,89); RED=RGBColor(174,70,64)

def textbox(slide,x,y,w,h,text,size=16,color=TEXT,bold=False,align=PP_ALIGN.LEFT,font='Aptos',margin=.08):
    sh=slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); tf=sh.text_frame; tf.clear(); tf.word_wrap=True
    tf.margin_left=tf.margin_right=Inches(margin); tf.margin_top=tf.margin_bottom=Inches(margin)
    for i,line in enumerate(text.split('\n')):
        p=tf.paragraphs[0] if i==0 else tf.add_paragraph(); p.text=line; p.font.name=font; p.font.size=Pt(size); p.font.bold=bold; p.font.color.rgb=color; p.alignment=align; p.space_after=Pt(5)
    return sh
def rect(slide,x,y,w,h,fill=WHITE,line=LINE,radius=True):
    sh=slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)); sh.fill.solid(); sh.fill.fore_color.rgb=fill
    sh.line.color.rgb=line; sh.line.width=Pt(1); return sh
def card(slide,x,y,w,h,title,body,accent=BLUE,body_size=15):
    rect(slide,x,y,w,h); rect(slide,x,y,.09,h,accent,accent,False)
    textbox(slide,x+.22,y+.16,w-.42,.38,title,17,NAVY,True)
    textbox(slide,x+.22,y+.63,w-.42,h-.72,body,body_size,TEXT)
def arrow(slide,x1,y1,x2,y2,color=BLUE,width=2):
    a=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2)); a.line.color.rgb=color; a.line.width=Pt(width); a.line.end_arrowhead=True
def notes(slide,duration,points,transition):
    slide.notes_slide.notes_text_frame.text=f"Suggested duration: {duration}\n\nSpeaking points:\n{points}\n\nTransition:\n{transition}"
def base(title,tag=None,subtitle=None):
    s=prs.slides.add_slide(blank); s.background.fill.solid(); s.background.fill.fore_color.rgb=BG
    textbox(s,.55,.2,11.3,.24,'INT450  •  TEAM T11  •  FINTECH AGENT',10,BLUE,True)
    textbox(s,.55,.48,11.4,.48,title,25,NAVY,True)
    if subtitle: textbox(s,.58,1.0,11.4,.3,subtitle,12,MUTED)
    if tag:
        sh=rect(s,11.12,.32,1.67,.42,ORANGE,ORANGE); tf=sh.text_frame; tf.clear(); tf.vertical_anchor=MSO_ANCHOR.MIDDLE
        p=tf.paragraphs[0]; p.text=tag; p.alignment=PP_ALIGN.CENTER; p.font.size=Pt(11); p.font.bold=True; p.font.color.rgb=WHITE
    textbox(s,.55,7.12,12.1,.18,'SASTRA DEEMED UNIVERSITY  •  OCTOBER 2026',9,MUTED)
    textbox(s,12.35,7.1,.4,.2,str(len(prs.slides)),9,MUTED,align=PP_ALIGN.RIGHT)
    return s

# 1 Cover
s=prs.slides.add_slide(blank); s.background.fill.solid(); s.background.fill.fore_color.rgb=BG
rect(s,0,0,13.333,.18,NAVY,NAVY,False); rect(s,.72,.8,11.9,5.95,WHITE,LINE)
textbox(s,1.15,1.25,10.7,.32,'INT450  /  LARGE LANGUAGE MODELS & AGENTIC AI',14,ORANGE,True)
textbox(s,1.12,2.0,10.8,1.05,'FinTech Agent',38,NAVY,True)
textbox(s,1.15,3.08,10.4,.86,'Natural-language access to synthetic banking data\nthrough a documented agentic query workflow',22,BLUE)
textbox(s,1.15,4.7,10.6,1.1,'Team T11  •  Guru S (125003001)  •  Jayavignesh J (125003002)  •  Anbu Selvan M (125003003)\nCourse faculty: Dr. K. Ramkumar  •  School of Computing  •  SASTRA Deemed University',13,MUTED)
textbox(s,1.15,6.12,10,.3,'Project review  |  October 2026',12,TEAL,True)
notes(s,'0:35','Introduce the project and team. State that the demonstrated data asset in the workspace is a synthetic banking dataset; the implementation status is summarized from the supplied design and source artifacts.','Start with the access problem the system is intended to address.')

# 2 Problem
s=base('Problem definition: business questions meet document queries','Rubric C1 · 4 marks','A practical interface problem for operations, risk and compliance analysts')
card(s,.65,1.55,3.75,2.15,'Users','Banking operations and risk staff need ad-hoc answers from linked customer, account, transaction and loan records.',BLUE)
card(s,4.78,1.55,3.75,2.15,'Friction','The dataset is document-oriented and linked by domain IDs. Questions spanning collections require query syntax and joins via aggregation.',TEAL)
card(s,8.9,1.55,3.75,2.15,'Need','Translate plain English into a read-only query, ground it in the schema, execute safely and explain the result.',ORANGE)
rect(s,.65,4.08,12,1.65,PALE,LINE); textbox(s,.9,4.35,11.45,.98,'Problem statement\nGiven an analyst’s natural-language question, produce a schema-grounded MongoDB aggregation and a useful answer; reject unsupported or unsafe requests.',19,NAVY,True)
textbox(s,.8,6.08,11.5,.45,'Example from the supplied benchmark: “Which customers have an annual income above ₹10 lakh, sorted by income descending?”',14,MUTED)
notes(s,'0:55','Describe the intended users and the difference between understanding a banking question and expressing it as a valid aggregation. Avoid unsupported claims about industry turnaround times.','The project goal turns this pain point into measurable objectives.')

# 3 objectives
s=base('Objectives and scope','Rubric C1 · 4 marks','The available workspace supports a dataset and benchmark definition; runtime outcome metrics are not included.')
items=[('01','Represent banking data','12 collections; synthetic INR domain; 55 benchmark questions.'),('02','Ground query generation','Use schema and relationship metadata to support field and join selection.'),('03','Constrain execution','Design read-only query validation and result checking before answering.'),('04','Evaluate honestly','Compare generated queries to a gold set; report measured scores only when run evidence exists.')]
for i,(n,t,b) in enumerate(items):
    y=1.5+i*1.13; rect(s,.75,y,.66,.66,PALE,LINE); textbox(s,.8,y+.14,.56,.3,n,15,BLUE,True,PP_ALIGN.CENTER)
    textbox(s,1.65,y-.02,3.3,.36,t,16,NAVY,True); textbox(s,5.0,y-.02,7.3,.53,b,15,TEXT)
rect(s,.75,6.08,5.8,.6,RGBColor(240,248,244),LINE); textbox(s,1,6.22,5.3,.3,'IN SCOPE  •  Dataset, query workflow design, evaluation plan',12,GREEN,True)
rect(s,6.8,6.08,5.8,.6,RGBColor(253,243,239),LINE); textbox(s,7.02,6.22,5.35,.3,'TO CONFIRM  •  Running app, metrics, scheduler and demo',12,RED,True)
notes(s,'0:55','Separate measurable project objectives from completed evidence. Dataset files define 55 questions, but the source tree provided does not include a runnable agent or evaluation output.','The agent design is motivated by multi-step grounding, validation and execution needs.')

# 4 agent rationale
s=base('Why an agent workflow?','Rubric C3 · 8 marks','Distinct steps make the query process inspectable and allow deterministic checks')
rect(s,.75,1.55,5.55,3.85,WHITE,LINE); textbox(s,1.05,1.8,4.9,.4,'Single-pass generation',20,NAVY,True)
textbox(s,1.05,2.45,4.8,2.3,'• Mixes intent, schema selection and query syntax in one step\n• No explicit gate between generated query and execution\n• Hard to diagnose incorrect fields or unsupported requests',16,TEXT)
rect(s,6.95,1.55,5.55,3.85,PALE,LINE); textbox(s,7.25,1.8,4.9,.4,'Documented graph approach',20,NAVY,True)
textbox(s,7.25,2.45,4.8,2.7,'• Retrieve relevant schema\n• Generate an aggregation\n• Validate before execution\n• Inspect results and retry on recoverable errors\n• Format a grounded answer',16,TEXT)
textbox(s,1.05,5.82,11.3,.6,'Design rationale: each transition creates a point to observe, test and fail closed. The supplied workspace documents this architecture; runtime evidence is not present.',15,ORANGE,True)
notes(s,'0:55','Explain that “agentic” here refers to stateful, conditional orchestration described in design docs—not a claim that agent code was found in the supplied project folder.','Next, inspect the data and knowledge sources this workflow is intended to use.')

# 5 data
s=base('Data and knowledge sources','Rubric C2 · 4 marks','Synthetic reference data avoids using personal banking records')
stats=[('12','collections'),('18,700+','default documents'),('55','benchmark questions'),('2010–2026','documented date span')]
for i,(v,l) in enumerate(stats):
    x=.75+i*3.1; rect(s,x,1.55,2.75,1.25,WHITE,LINE); textbox(s,x+.15,1.72,2.45,.48,v,25,BLUE,True,PP_ALIGN.CENTER); textbox(s,x+.15,2.25,2.45,.28,l,12,MUTED,align=PP_ALIGN.CENTER)
card(s,.75,3.15,5.55,2.4,'Sources in workspace','Faker-based generator and validation scripts; JSON schema with fields, allowed values, integrity rules and relationships; CSV/JSON exports.',TEAL,15)
card(s,6.95,3.15,5.55,2.4,'Domain coverage','Customers, accounts, transactions, loans, cards, merchants, branches, employees, KYC, support tickets, fraud alerts and investments.',BLUE,15)
textbox(s,.9,5.95,11.5,.6,'Known limitations: synthetic data; one domain; benchmark questions are defined, but no run log or held-out split was supplied.',14,ORANGE,True)
notes(s,'0:55','Numbers are from README_DATASET.md and test_questions.json metadata. The default count is approximate; the listed per-collection defaults sum to 18,120, so avoid claiming a precise generated total unless measured from an actual database run.','Now follow the documented architecture from question to answer.')

# 6 architecture diagram
s=base('System architecture: documented design','Rubric C3 · 8 marks','LLM-generated content is separated from code-controlled validation and data access')
nodes=[(.55,2.12,1.62,1.05,'Analyst','Natural-language\nquestion',PALE,BLUE),(2.52,2.12,1.72,1.05,'API layer','FastAPI /\nsession state',WHITE,TEAL),(4.58,2.12,1.9,1.05,'Agent graph','Intent → schema →\nquery generation',PALE,BLUE),(6.82,2.12,1.88,1.05,'Safety gate','Syntax / operator /\npolicy validation',RGBColor(240,248,244),GREEN),(9.05,2.12,1.7,1.05,'MongoDB','Read-only\naggregation',WHITE,TEAL),(11.07,2.12,1.7,1.05,'Answer','Verified results +\nexplanation',PALE,BLUE)]
for x,y,w,h,t,b,fill,ac in nodes:
    rect(s,x,y,w,h,fill,LINE); textbox(s,x+.08,y+.12,w-.16,.28,t,14,ac,True,PP_ALIGN.CENTER); textbox(s,x+.08,y+.48,w-.16,.48,b,11,TEXT,align=PP_ALIGN.CENTER)
for x1,x2 in [(2.18,2.48),(4.26,4.54),(6.5,6.78),(8.72,9.0),(10.78,11.03)]: arrow(s,x1,2.65,x2,2.65)
rect(s,3.0,4.12,3.0,1.05,RGBColor(239,247,248),LINE); textbox(s,3.2,4.32,2.6,.55,'Schema / relationship\nknowledge source',14,TEAL,True,PP_ALIGN.CENTER)
arrow(s,4.5,4.08,5.1,3.22,TEAL)
rect(s,7.05,4.12,3.15,1.05,RGBColor(253,243,239),LINE); textbox(s,7.25,4.32,2.75,.55,'Error / result feedback\nconditional retry',14,ORANGE,True,PP_ALIGN.CENTER)
arrow(s,8.6,3.22,8.6,4.08,ORANGE); arrow(s,7.0,4.65,5.95,3.25,ORANGE)
textbox(s,.85,5.73,11.6,.56,'Technology named in project design: LangGraph • FastAPI • MongoDB • Redis • Celery. Implemented status was not independently verifiable in the supplied source tree.',13,MUTED,True,PP_ALIGN.CENTER)
notes(s,'1:05','Walk left to right. Blue marks model or orchestration work; green marks deterministic validation; the lower loop represents the documented retry path. The diagram is a design view, not a screenshot or proof of a deployed stack.','Each stage has a distinct responsibility, summarized next.')

# 7 roles
s=base('Agent stages and tool responsibilities','Rubric C3 · 8 marks','The supplied design describes a single stateful workflow with specialized nodes')
headers=['Stage','Responsibility','Evidence / output']
rows=[('Intent gate','Classify query vs. unsupported intent','Route or clarify'),('Schema retrieval','Select relevant collections and fields','Schema context'),('Query generation','Produce MQL aggregation','Pipeline draft'),('Validation & execution','Check allowed operations; execute with limits','Pass / block + result'),('Result review','Check plausibility; retry recoverable errors','Accepted result or abstention'),('Answer formatting','Summarize results in business language','Answer + query trace')]
for j,h in enumerate(headers):
    x=[.8,3.55,8.35][j]; w=[2.65,4.65,4.1][j]; rect(s,x,1.55,w,.52,NAVY,NAVY,False); textbox(s,x+.08,1.68,w-.16,.24,h,12,WHITE,True)
for i,row in enumerate(rows):
    y=2.07+i*.66; fill=WHITE if i%2==0 else RGBColor(241,245,249)
    for j,txt in enumerate(row):
        x=[.8,3.55,8.35][j]; w=[2.65,4.65,4.1][j]; rect(s,x,y,w,.66,fill,LINE,False); textbox(s,x+.1,y+.13,w-.2,.39,txt,12,NAVY if j==0 else TEXT,j==0)
textbox(s,.9,6.28,11.5,.36,'Scheduling is described in design materials; no scheduler source code or executable configuration is present in fintech-agent/.',13,ORANGE,True)
notes(s,'0:55','Use “stages” rather than implying separate autonomous agent models. Distinguish documented node roles from implementation evidence.','Let us trace a representative benchmark request through those stages.')

# 8 E2E
s=base('One request, end to end','Rubric C3 + C4 · 16 marks','A real question from the supplied 55-item benchmark')
rect(s,.75,1.45,11.8,.72,PALE,LINE); textbox(s,1.0,1.62,11.25,.34,'“Which customers have an annual income above ₹10 lakh, sorted by income descending?”',17,NAVY,True,PP_ALIGN.CENTER)
stages=[('01  Understand','Filter customers by annual_income > 1,000,000.'),('02  Ground','Confirm collection, field and numeric type in schema.'),('03  Generate','Draft $match and descending $sort stages.'),('04  Validate','Check pipeline structure and read-only policy.'),('05  Return','Execute, inspect rows and explain the result.')]
for i,(t,b) in enumerate(stages):
    x=.62+i*2.54; rect(s,x,2.75,2.25,2.0,WHITE,LINE); textbox(s,x+.13,3.0,1.98,.32,t,14,BLUE,True,PP_ALIGN.CENTER); textbox(s,x+.16,3.5,1.93,1.05,b,12,TEXT,align=PP_ALIGN.CENTER)
    if i<4: arrow(s,x+2.27,3.75,x+2.49,3.75)
textbox(s,.95,5.35,11.3,.85,'Illustrative expected pipeline shape:  [{ $match: { annual_income: { $gt: 1000000 } } }, { $sort: { annual_income: -1 } } ]\nThis is a benchmark-derived example, not a captured application output.',14,MUTED,align=PP_ALIGN.CENTER)
notes(s,'1:05','Explain the transformation and point out the sort direction and threshold. The example query comes from Q11 in test_questions.json. This slide shows the intended path, not a measured live execution.','The quality of this pipeline depends on explicit guardrails.')

# 9 safety
s=base('Safety, guardrails and verification','Rubric C5 · 5 marks','The design calls for code-enforced controls around model output')
controls=[('Input guard','Detect unsupported or ambiguous intent; request clarification.'),('Action gate','Allow only a read-only subset of MongoDB aggregation operators.'),('Execution limit','Use bounded results, timeouts and index/performance checks.'),('Output verification','Inspect execution outcome; retry bounded errors or abstain.'),('Auditability','Expose the generated query and validation decision for review.')]
for i,(t,b) in enumerate(controls):
    x=.8+(i%2)*6.05; y=1.55+(i//2)*1.48
    card(s,x,y,5.55,1.18,t,b,[BLUE,TEAL,GREEN,ORANGE,NAVY][i],13)
rect(s,6.85,4.51,5.55,1.18,RGBColor(253,243,239),LINE); textbox(s,7.08,4.72,5.05,.78,'Verification boundary\nThe source tree does not contain the validator or tests; zero-write and latency guarantees remain unverified.',13,RED,True)
textbox(s,.95,6.2,11.3,.42,'Core principle: the model proposes a query; deterministic application code should decide whether it may execute.',15,NAVY,True,PP_ALIGN.CENTER)
notes(s,'0:55','Describe the controls as requirements/design. Avoid calling them verified controls until the relevant code and test output are available.','The planned live demo should make one successful path and one blocked path visible.')

# 10 demo
s=base('Implementation and demo plan','Rubric C4 · 8 marks','No runnable application code or interface screenshot was present in the provided workspace')
card(s,.8,1.55,3.75,2.3,'Normal case','Ask Q11; show generated pipeline, validation decision and returned records.',BLUE,14)
card(s,4.8,1.55,3.75,2.3,'Tricky case','Ask a multi-collection Level 4/5 benchmark question; inspect schema grounding and query behavior.',TEAL,14)
card(s,8.8,1.55,3.75,2.3,'Refusal case','Try an unsafe or out-of-scope request; show the actual rejection path.',ORANGE,14)
rect(s,.8,4.35,11.75,1.25,RGBColor(253,243,239),LINE); textbox(s,1.05,4.58,11.2,.7,'Demo status: to be supplied by the team. Use a real run or clearly label this walkthrough as a design demonstration.',17,RED,True,PP_ALIGN.CENTER)
textbox(s,1.0,6.12,11.2,.4,'The benchmark includes 55 questions across five complexity levels; the files provide questions, not run results.',14,MUTED,True,PP_ALIGN.CENTER)
notes(s,'0:55','If a runnable implementation becomes available, demonstrate the normal, tricky and refusal cases. Until then, state that the current artifacts establish the data and design, not an operational demo.','We can still define a transparent evaluation protocol from the supplied benchmark.')

# 11 methodology
s=base('Evaluation methodology','Rubric C6 · 7 marks','The benchmark is specified; execution metrics are absent')
steps=[('Gold set','55 questions, five levels'),('Run','Record generated pipeline, errors, latency'),('Judge','Compare result semantics to expected query/output'),('Report','Break down accuracy and failure types by level')]
for i,(t,b) in enumerate(steps):
    x=.75+i*3.1; rect(s,x,1.75,2.72,1.65,WHITE,LINE); textbox(s,x+.16,1.99,2.4,.36,t,18,BLUE,True,PP_ALIGN.CENTER); textbox(s,x+.18,2.52,2.36,.58,b,14,TEXT,align=PP_ALIGN.CENTER)
    if i<3: arrow(s,x+2.75,2.58,x+3.02,2.58)
rect(s,.85,4.05,11.65,1.45,PALE,LINE); textbox(s,1.1,4.3,11.15,.95,'Recommended measures: execution accuracy • exact/semantic match • abstention correctness • unsafe-query rejection • median/P95 latency • retry recovery rate',17,NAVY,True,PP_ALIGN.CENTER)
textbox(s,1.0,5.95,11.2,.45,'Baseline and held-out split are not documented in the available benchmark file; define them before reporting comparative results.',14,ORANGE,True,PP_ALIGN.CENTER)
notes(s,'0:55','The test_questions.json metadata reports 55 items grouped into five complexity tiers. No evaluation harness, gold outputs, baseline or measured results are included in the provided files.','That evidence gap determines how results and failure analysis should be presented.')

# 12 results
s=base('Results and failure analysis','Rubric C6 · 7 marks','Report evidence only; do not substitute target values for measured outcomes')
rect(s,.8,1.55,5.7,2.6,WHITE,LINE); textbox(s,1.15,1.85,5.0,.4,'Evidence available',20,NAVY,True); textbox(s,1.15,2.45,5.0,1.2,'• Dataset generator and schema\n• 55-question benchmark definition\n• Data validation scripts',16,TEXT)
rect(s,6.8,1.55,5.7,2.6,RGBColor(253,243,239),LINE); textbox(s,7.15,1.85,5.0,.4,'Evidence missing',20,RED,True); textbox(s,7.15,2.45,5.0,1.35,'• Agent execution logs\n• Accuracy / latency measurements\n• Failure counts and baseline comparison',16,TEXT)
textbox(s,1.0,4.75,11.2,.7,'Failure cases to investigate: incorrect field/value mapping • null or polymorphic fields • wrong $lookup path • empty result mistaken for a valid answer • unsafe operator attempt.',15,BLUE,True,PP_ALIGN.CENTER)
textbox(s,1.0,5.85,11.2,.65,'Before final review, attach a reproducible evaluation run and replace this evidence-gap slide with measured results and representative failures.',14,ORANGE,True,PP_ALIGN.CENTER)
notes(s,'0:55','Be candid: the supplied deck drafts contain numerical claims, but the code and logs needed to substantiate them are not in the project implementation folder. Do not present those figures as results without confirming evidence.','We now align the project evidence with the report and the team’s actual contributions.')

# 13 alignment/team
s=base('Report alignment and individual contribution','Rubric C7 · IEEE report alignment  |  C9 · 5 marks')
card(s,.8,1.55,5.55,2.15,'Report alignment','Use one naming convention and architecture across slides and report. Cite dataset/schema artifacts and evaluation method. No IEEE report or reference list was included for cross-checking.',TEAL,14)
card(s,6.85,1.55,5.55,2.15,'Contribution evidence','The draft names three members and assigns modules, but the source tree does not verify those assignments. Confirm each member’s delivered artifact and speaking range.',ORANGE,14)
people=[('Guru S','125003001','Confirm module + slides'),('Jayavignesh J','125003002','Confirm module + slides'),('Anbu Selvan M','125003003','Confirm module + slides')]
for i,(n,r,c) in enumerate(people):
    x=.85+i*4.12; rect(s,x,4.25,3.75,1.3,WHITE,LINE); textbox(s,x+.16,4.45,3.42,.3,n,17,NAVY,True,PP_ALIGN.CENTER); textbox(s,x+.16,4.85,3.42,.25,r+'  •  '+c,11,MUTED,align=PP_ALIGN.CENTER)
textbox(s,1,6.1,11.2,.42,'C8 communication: one message per slide, visible diagrams, explicit evidence boundaries and a timed 15-minute story.',14,BLUE,True,PP_ALIGN.CENTER)
notes(s,'0:50','Ask the team to confirm member modules and update slide assignments. C7 asks for alignment with the IEEE-style project report; the report itself was not present here, so this deck avoids invented references.','The final slide summarizes the project’s contribution and concrete next steps.')

# 14 conclusion
s=base('Conclusion and next steps','Rubric C8 · Presentation and communication')
card(s,.8,1.55,5.55,2.45,'What is established','A synthetic, relational banking dataset; a schema and integrity contract; and a 55-question benchmark spanning five query complexity levels.',BLUE,15)
card(s,6.85,1.55,5.55,2.45,'What comes next','Provide the runtime implementation; execute and report the benchmark; verify safety controls; capture genuine demo evidence; confirm contributions and report citations.',TEAL,15)
rect(s,.8,4.55,11.75,1.25,PALE,LINE); textbox(s,1.1,4.8,11.1,.7,'FinTech Agent is designed to turn banking questions into schema-grounded MongoDB queries, with validation between model output and database execution.',18,NAVY,True,PP_ALIGN.CENTER)
textbox(s,1.0,6.2,11.2,.35,'Thank you  •  Questions?',18,ORANGE,True,PP_ALIGN.CENTER)
notes(s,'0:35','Close with the project’s concrete foundation and the next evidence needed to validate the full system. Invite questions and be ready to explain schema relationships, benchmark design and safety requirements.','Open the floor for individual questions and contribution review.')

prs.save(OUT/'INT450_Final_Project_Presentation.pptx')
print('saved',OUT/'INT450_Final_Project_Presentation.pptx','slides',len(prs.slides))

# Text2SQL을 위한 데이터베이스 구조 설명서

- 버전: v0.0.0
- 작성: 김예찬, 주종민
- 변경 이력:
  - 2026-03-03, v0.0.0 초안 작성


## 사용 데이터베이스 엔진
- **SQLite3**
  - Text2SQL 시 SQLite3의 문법을 준수할 것. 


## SQL 변환 시 유의사항
- 아래 **테이블 구조**를 반드시 확인하여, 자연어 텍스트 질의에 답변하기 위해 필요한 테이블을 1개 이상 선택할 것.
- 필요 시 Join 연산을 사용하되, 너무 과도한 Join 연산은 가급적 자제할 것.
- 중복 결과가 발생하면, 우선 Join 조건이 올바른지 검토하고, 최후의 수단으로 Distinct를 사용할 것.
- NULL 비교는 반드시 IS NULL 혹은 IS NOT NULL을 사용하고, =NULL은 절대 사용하지 않을 것.
- 자연어 질문을 SQL로 변환하기 전, 질문이 목록 조회인지, 집계 (Aggregation)인지 그 성격을 우선 파악할 것.
- 0으로 나누는 상황이 예상되면, 예외 처리 조건을 추가할 것.
- 자연어 질문이 모호하게 제시될 경우, 가장 보수적이고 안전한 해석을 추구할 것.
- SQL 쿼리로 변환한 결과를 사용자에게 제시하기 전, 해당 쿼리의 실행 결과와 SQL 코드를 바탕으로, 이것이 사용자의 질문과 대응하는지 재고할 것.


## 테이블 구조
- 본 연구에서 사용하는 테이블 유형은 다음과 같다:
  - snapshots
  - groups
  - vehicles
  - vehicles_ammo
  - vehicles_hitpoints
  - units
  - units_ammo
  - event_dammaged
  - event_fired
  - event_killed
  - event_knowsaboutchanged


### snapshots 테이블
- 특별한 경우가 아닌한, Text2SQL에서 사용할 필요가 없는 테이블. 중복된 스냅샷 저장을 막기 위해 존재하는 데이터 구조.
- 컬럼
  - `snapshotid`: 각 스냅샷에 부여된 고유의 식별 ID.
  - `sourcefile`: 해당 스냅샷의 원본 json 파일. (Text2SQL 시 필요한 컬럼이 아니므로, 무시할 것)
  - `datetime`: 현재 스냅샷 (현재 `snapshotid`)의 일시. (ISO8601 포맷 준수: {YYYY}-{MM}-{DD}T-{HH}-{MM}-{SS}.SSS 꼴) (예로, 2026-03-03T14:04:54.605는 2026년 3월 3일 14시 4분 54초 605밀리초)
  - `rawjson`: 해당 스냅샷의 원본 json 파일의 json 텍스트.
  - `sha256`: `rawjson`에 대한 해싱 값. (중복된 json 콘텐츠 저장 여부 확인용) (Text2SQL 시 필요한 컬럼이 아니므로, 무시할 것)


### groups 테이블
- 특정 스냅샷 시점에서 관측된 "**그룹 (중대-소대-분대 단위)**"의 정보를 저장. 
- 구체적으로, 특정 시점 (`datetime`)마다의 `groupname` (side, company, platoon, squad를 모두 포괄)이라는 **그룹의 식별자** 및 각 그룹의 **리더의 위치** (`leaderposx`, `leaderposy`, `leaderposz`), 그리고 각 그룹의 **목적지** (`waypointx`, `waypointz`)가 함께 저장됨.
- 컬럼
  - `snapshotid`: 각 스냅샷에 부여된 고유의 식별 ID.
  - `side`: `b` 또는 `op` 값이 저장됨. 아군 (`b`) 및 적군 (`op`)을 구분하기 위한 식별자.
  - `company`: 아군 및 적군 하의 "중대" 식별자.
  - `platoon`: 아군 및 적군 하의 "소대" 식별자.
  - `squad`: 아군 및 적군 하의 "분대" 식별자. 
  - `groupname`: f"{side}_{company}_{platoon}_{squad}" 꼴의 문자열.  
  - `datetime`: 현재 스냅샷 (현재 `snapshotid`)의 일시 (ISO8601 포맷 준수: {YYYY}-{MM}-{DD}T-{HH}-{MM}-{SS}.SSS 꼴) (예로, 2026-03-03T14:04:54.605는 2026년 3월 3일 14시 4분 54초 605밀리초)
  - `leaderposx`: (현재 스냅샷 시점의) 각 그룹의 리더의 위치의 x좌표.
  - `leaderposy`: (현재 스냅샷 시점의) 각 그룹의 리더의 위치의 y좌표.
  - `leaderposz`: (현재 스냅샷 시점의) 각 그룹의 리더의 위치의 z좌표.
  - `waypointposx`: (현재 스냅샷 시점의) 각 그룹의 목적지의 x좌표.
  - `waypointposy`: (현재 스냅샷 시점의) 각 그룹의 목적지의 y좌표.


### vehicles 테이블
- 특정 스냅샷 시점에서 관측된 "**차량 상태**" 정보를 저장. 
- 차량은 `vehiclename` 컬럼으로 식별하며, 소속 그룹은 groups 테이블의 `groupname`을 사용하여 알 수 있음.
- 또한, 차량 모델명 (`vehicletype`), 특정 시점의 차량 위치 (`posx`, `posy`, `posz`) 및 차량의 손상 정도 (`damage`) 등을 저장.
- 컬럼
  - `snapshotid`: 각 스냅샷에 부여된 고유의 식별 ID.
  - `datetime`: 현재 스냅샷 (현재 `snapshotid`)의 일시 (ISO8601 포맷 준수: {YYYY}-{MM}-{DD}T-{HH}-{MM}-{SS}.SSS 꼴) (예로, 2026-03-03T14:04:54.605는 2026년 3월 3일 14시 4분 54초 605밀리초)
  - `side`: `b` 또는 `op` 값이 저장됨. 아군 (`b`) 및 적군 (`op`)을 구분하기 위한 식별자.
  - `vehiclename`: 차량에 대한 고유 식별 ID. (Tip: 통상 f"_v{숫자}" 꼴의 Suffix를 갖는 문자열.)
  - `groupname`: f"{side}_{company}_{platoon}_{squad}" 꼴의 문자열.  
  - `posx`: (현재 스냅샷 시점의) 각 차량의 위치의 x좌표.
  - `posy`: (현재 스냅샷 시점의) 각 차량의 위치의 y좌표.
  - `posz`: (현재 스냅샷 시점의) 각 차량의 위치의 z좌표.
  - `damage`: (현재 스냅샷 시점의) 각 차량의 손상 정도. (0 이상 1 이하의 값, 0에 가까울 수록 "피해가 없다", 1에 가까울수록 "피해가 매우 크다"를 의미)
  - `hitpointjson`: 디버깅 용도. Text2SQL 시 필요한 컬럼이 아니므로, 무시할 것.


### vehicles_hitpoints 테이블
- 특정 스냅샷 시점에서 관측된 각 차량의 "**주요 부위 (`hitpoint`)별 손상 정도**"를 저장.
- 컬럼
  - `snapshotid`: 각 스냅샷에 부여된 고유의 식별 ID.
  - `datetime`: 현재 스냅샷 (현재 `snapshotid`)의 일시 (ISO8601 포맷 준수: {YYYY}-{MM}-{DD}T-{HH}-{MM}-{SS}.SSS 꼴) (예로, 2026-03-03T14:04:54.605는 2026년 3월 3일 14시 4분 54초 605밀리초)
  - `side`: `b` 또는 `op` 값이 저장됨. 아군 (`b`) 및 적군 (`op`)을 구분하기 위한 식별자.
  - `vehiclename`: 차량에 대한 고유 식별 ID. (Tip: 통상 f"_v{숫자}" 꼴의 Suffix를 갖는 문자열.)
  - `hitpoint`: (현재 스냅샷 시점의) 차량의 특정 부위.
  - `damage`: (현재 스냅샷 시점의) 차량의 특정 부위가 손상된 정도. (0 이상 1 이하의 값, 0에 가까울 수록 "피해가 없다", 1에 가까울수록 "피해가 매우 크다"를 의미)


### vehicles_ammo 테이블
- 특정 스냅샷 시점에서 관측된 각 "**차량이 보유한 탄약을 탄종**"별로 저장.
- 구체적으로, 차량-탄종 (`vehiclename`-`ammotype`) 조합으로 집계된 결과 (`count`: 현재 특정 차량의 탄종별 탄약 개수)가 저장됨.
- 컬럼
  - `snapshotid`: 각 스냅샷에 부여된 고유의 식별 ID.
  - `datetime`: 현재 스냅샷 (현재 `snapshotid`)의 일시 (ISO8601 포맷 준수: {YYYY}-{MM}-{DD}T-{HH}-{MM}-{SS}.SSS 꼴) (예로, 2026-03-03T14:04:54.605는 2026년 3월 3일 14시 4분 54초 605밀리초)
  - `side`: `b` 또는 `op` 값이 저장됨. 아군 (`b`) 및 적군 (`op`)을 구분하기 위한 식별자.
  - `vehiclename`: 차량에 대한 고유 식별 ID. (Tip: 통상 f"_v{숫자}" 꼴의 Suffix를 갖는 문자열.)
  - `ammotype`: 탄종.
  - `count`: 차량-탄종 (`vehiclename`-`ammotype`) 조합으로 집계된 결과, 즉 현재 특정 차량의 탄종별 탄약 개수.


### units 테이블
- 특정 스냅샷 시점에서 관측된 "**개별 유닛 (병사)**" 정보를 저장. 
- 유닛 (병사)는 `unitname` 컬럼으로 식별하며, 소속 그룹은 groups 테이블의 `groupname`을 사용하여 알 수 있음.
- 또한, 유닛 타입 (`unittype`), 특정 시점의 유닛 위치 (`posx`, `posy`, `posz`) 및 유닛의 손상 정도 (`damage`) 등을 저장. 유닛이 특정 차량에 탑승 중인 경우 `objectparent`에 특정 차량 ID인 vehicles 테이블의 `vehiclename`이 저장됨.
- 컬럼
  - `snapshotid`: 각 스냅샷에 부여된 고유의 식별 ID.
  - `datetime`: 현재 스냅샷 (현재 `snapshotid`)의 일시 (ISO8601 포맷 준수: {YYYY}-{MM}-{DD}T-{HH}-{MM}-{SS}.SSS 꼴) (예로, 2026-03-03T14:04:54.605는 2026년 3월 3일 14시 4분 54초 605밀리초)
  - `side`: `b` 또는 `op` 값이 저장됨. 아군 (`b`) 및 적군 (`op`)을 구분하기 위한 식별자.
  - `unit`: 유닛에 대한 고유 식별 ID. (Tip: 통상 f"_u{숫자}" 꼴의 Suffix를 갖는 문자열.)
  - `groupname`: f"{side}_{company}_{platoon}_{squad}" 꼴의 문자열.  
  - `posx`: (현재 스냅샷 시점의) 각 유닛의 위치의 x좌표.
  - `posy`: (현재 스냅샷 시점의) 각 유닛의 위치의 y좌표.
  - `posz`: (현재 스냅샷 시점의) 각 유닛의 위치의 z좌표.
  - `damage`: (현재 스냅샷 시점의) 각 유닛의 손상 정도. (0 이상 1 이하의 값, 0에 가까울 수록 "피해가 없다", 1에 가까울수록 "피해가 매우 크다"를 의미)
  - `objectparent`: (현재 스냅샷 시점의) 각 유닛이 타고 있는 차량 정보. (차량 탑승 시에만 값이 저장됨.)


### units_ammo 테이블
- 특정 스냅샷 시점에서 관측된 각 "**유닛이 보유한 탄약을 탄종**"별로 저장.
- 구체적으로, 유닛(병사)-탄종 (`unitname`-`ammotype`) 조합으로 집계된 결과 (`count`: 현재 특정 유닛의 탄종별 탄약 개수)가 저장됨.
- 컬럼
  - `snapshotid`: 각 스냅샷에 부여된 고유의 식별 ID.
  - `datetime`: 현재 스냅샷 (현재 `snapshotid`)의 일시 (ISO8601 포맷 준수: {YYYY}-{MM}-{DD}T-{HH}-{MM}-{SS}.SSS 꼴) (예로, 2026-03-03T14:04:54.605는 2026년 3월 3일 14시 4분 54초 605밀리초)
  - `side`: `b` 또는 `op` 값이 저장됨. 아군 (`b`) 및 적군 (`op`)을 구분하기 위한 식별자.
  - `unitname`: 차량에 대한 고유 식별 ID. (Tip: 통상 f"_v{숫자}" 꼴의 Suffix를 갖는 문자열.)
  - `ammotype`: 탄종.
  - `count`: 유닛(병사)-탄종 (`unitname`-`ammotype`) 조합으로 집계된 결과, 즉 현재 특정 유닛의 탄종별 탄약 개수.


### event_knowsaboutchanged 테이블
- 특정 스냅샷 시점에서 이벤트 핸들러인 "**KnowsAboutChanged**" 로그를 저장.
- **관측 주체(그룹)**가 **특정 타겟(유닛/차량)**에 대해 가지고 있는 인지 수준(knowsAbout)이 변경된 순간들을 기록. 즉 "누가(관측 그룹) 누구를(타겟) 얼마나 알고 있는지"가 시간에 따라 업데이트될 때마다 로그가 쌓임.
- 컬럼
  - `snapshotid`: 각 스냅샷에 부여된 고유의 식별 ID.
  - `datetime`: 현재 스냅샷 (현재 `snapshotid`)의 일시 (ISO8601 포맷 준수: {YYYY}-{MM}-{DD}T-{HH}-{MM}-{SS}.SSS 꼴) (예로, 2026-03-03T14:04:54.605는 2026년 3월 3일 14시 4분 54초 605밀리초)
  - `side`: `b` 또는 `op` 값이 저장됨. 아군 (`b`) 및 적군 (`op`)을 구분하기 위한 식별자.
  - `seq`: 같은 스냅샷/팀 내에서 이벤트 배열의 순번(중복 시간 대비용).
  - `groupname`: f"{side}_{company}_{platoon}_{squad}" 꼴의 문자열.  
  - `targetunit`: 관심 대상 타겟. (유의사항: unit이라고 변수명은 되어 있으나, vehicle 차량 장비도 저장될 수 있음!)
  - `oldknowsabout`: 변경 이전 knowsAbout 값. (0 이상 4 이하, 0에 가까울 수록 "거의 모른다/인지하지 못한다", 4에 가까울수록 "매우 잘 안다/정확히 인지한다". 실무적으로 **1 이상이면 ‘어느 정도 알고 있다(인지가 형성됨)’**로 볼 수 있음.)
  - `newknowsabout`: 변경 이후 knowsAbout 값.
  - `keyname`: 디버깅 용도. Text2SQL 시 필요한 컬럼이 아니므로, 무시할 것.
  - `paramsjson`: 디버깅 용도. Text2SQL 시 필요한 컬럼이 아니므로, 무시할 것.


### event_fired 테이블
- 교전 중, 특정 스냅샷 시점에서 발생한 **발사 (Fired) 이벤트**를 기록. 누가 (`gunner`) 누구 (`targetunit`)를 쏘았는지에 대한 정보.
- 컬럼
  - `snapshotid`: 각 스냅샷에 부여된 고유의 식별 ID.
  - `datetime`: 현재 스냅샷 (현재 `snapshotid`)의 일시 (ISO8601 포맷 준수: {YYYY}-{MM}-{DD}T-{HH}-{MM}-{SS}.SSS 꼴) (예로, 2026-03-03T14:04:54.605는 2026년 3월 3일 14시 4분 54초 605밀리초)
  - `side`: `b` 또는 `op` 값이 저장됨. 아군 (`b`) 및 적군 (`op`)을 구분하기 위한 식별자.
  - `seq`: 같은 스냅샷/팀 내에서 이벤트 배열의 순번(중복 시간 대비용).
  - `targetunit`: 피격 대상으로, 탄을 맞는 사람 혹은 장비. (유의사항: unit이라고 변수명은 되어 있으나, vehicle 차량 장비도 저장될 수 있음!)
  - `gunner`: 사격자 (발사 주체). 쏜 사람 혹은 장비. 
  - `ammotype`: 탄종.
  - `muzzle`: 포구 유형.
  - `keyname`: 디버깅 용도. Text2SQL 시 필요한 컬럼이 아니므로, 무시할 것.
  - `paramsjson`: 디버깅 용도. Text2SQL 시 필요한 컬럼이 아니므로, 무시할 것.


### event_dammaged 테이블
- 교전 중, 특정 스냅샷 시점에서 관측된 각 유닛/장비의 **피해 받은 (Damaged) 이벤트**를 기록. 누가 (`shooter`) 누구 (`targetunit`)에게 언제, 얼마나 피해를 가했는지에 대한 정보.
- 컬럼
  - `snapshotid`: 각 스냅샷에 부여된 고유의 식별 ID.
  - `datetime`: 현재 스냅샷 (현재 `snapshotid`)의 일시 (ISO8601 포맷 준수: {YYYY}-{MM}-{DD}T-{HH}-{MM}-{SS}.SSS 꼴) (예로, 2026-03-03T14:04:54.605는 2026년 3월 3일 14시 4분 54초 605밀리초)
  - `side`: `b` 또는 `op` 값이 저장됨. 아군 (`b`) 및 적군 (`op`)을 구분하기 위한 식별자.
  - `seq`: 같은 스냅샷/팀 내에서 이벤트 배열의 순번(중복 시간 대비용).
  - `targetunit`: 피격 대상으로, 탄을 맞는 사람 혹은 장비. (유의사항: unit이라고 변수명은 되어 있으나, vehicle 차량 장비도 저장될 수 있음!)
  - `shooter`: 가해자(발사/공격 주체).
  - `damage`: (현재 스냅샷 시점의) 각 유닛 혹은 장비의 손상 정도. (0 이상 1 이하의 값, 0에 가까울 수록 "피해가 없다", 1에 가까울수록 "피해가 매우 크다"를 의미)
  - `hitpoint`: (현재 스냅샷 시점의) 각 유닛 혹은 차량의 특정 부위.
  - `keyname`: 디버깅 용도. Text2SQL 시 필요한 컬럼이 아니므로, 무시할 것.
  - `paramsjson`: 디버깅 용도. Text2SQL 시 필요한 컬럼이 아니므로, 무시할 것.


### event_killed 테이블
- 교전 중, 특정 스냅샷 시점에서 발생한 **사망/격파 (Killed) 이벤트**를 기록. 누가 (`killer`/`instigator`) 누구 (`targetunit`)를 언제 (`datetime`) 죽였는지에 대한 정보.
- 컬럼
  - `snapshotid`: 각 스냅샷에 부여된 고유의 식별 ID.
  - `datetime`: 현재 스냅샷 (현재 `snapshotid`)의 일시 (ISO8601 포맷 준수: {YYYY}-{MM}-{DD}T-{HH}-{MM}-{SS}.SSS 꼴) (예로, 2026-03-03T14:04:54.605는 2026년 3월 3일 14시 4분 54초 605밀리초)
  - `side`: `b` 또는 `op` 값이 저장됨. 아군 (`b`) 및 적군 (`op`)을 구분하기 위한 식별자.
  - `seq`: 같은 스냅샷/팀 내에서 이벤트 배열의 순번(중복 시간 대비용).
  - `targetunit`: 피해자. 사망한 대상 (사람 혹은 장비). (유의사항: unit이라고 변수명은 되어 있으나, vehicle 차량 장비도 저장될 수 있음!)
  - `killer`: 직접적으로 죽인 사람 혹은 장비.
  - `instigator`: killer를 조종/유발한 사람 혹은 장비.
  - `keyname`: 디버깅 용도. Text2SQL 시 필요한 컬럼이 아니므로, 무시할 것.
  - `paramsjson`: 디버깅 용도. Text2SQL 시 필요한 컬럼이 아니므로, 무시할 것.


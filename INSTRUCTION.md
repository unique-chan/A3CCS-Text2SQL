# Text2SQL을 위한 데이터베이스 구조 설명서

- 버전: v0.0.0
- 작성: 김예찬, 주종민
- 변경 이력:
  - 2026-03-03, v0.0.0 초안 작성


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
  - `damage`: (현재 스냅샷 시점의) 각 차량의 손상 정도.
  - `hitpointjson`: 디버깅 용도. Text2SQL 시 필요한 컬럼이 아니므로, 무시할 것.

## vehicles_ammo 테이블
- 특정 스냅샷 시점에서 곽측된 각 "**차량이 보유한 탄약/탄창을 탄종**"별로 저장.
- 컬럼
  - `snapshotid`: 각 스냅샷에 부여된 고유의 식별 ID.
  - `datetime`: 현재 스냅샷 (현재 `snapshotid`)의 일시 (ISO8601 포맷 준수: {YYYY}-{MM}-{DD}T-{HH}-{MM}-{SS}.SSS 꼴) (예로, 2026-03-03T14:04:54.605는 2026년 3월 3일 14시 4분 54초 605밀리초)
  - `side`: `b` 또는 `op` 값이 저장됨. 아군 (`b`) 및 적군 (`op`)을 구분하기 위한 식별자.
  - `vehiclename`: 차량에 대한 고유 식별 ID. (Tip: 통상 f"_v{숫자}" 꼴의 Suffix를 갖는 문자열.)
  - `hitpoint`: (현재 스냅샷 시점의) 차량의 특정 부위
  - `damage`: (현재 스냅샷 시점의) 차량의 특정 부위가 손상된 정도

## vehicles_
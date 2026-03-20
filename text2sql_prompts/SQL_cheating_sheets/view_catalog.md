# View Catalog

이 문서는 LLM이 우선적으로 사용할 수 있는 미리 정의된 SQLite view를 설명한다.

운영 규칙:
- side='b' 는 아군, side='op' 는 적군이다.
- current 는 각 테이블에서 해당 side 기준 MAX(datetime) 시점을 뜻한다.
- initial 은 각 테이블에서 해당 side 기준 MIN(datetime) 시점을 뜻한다.
- unit_count / vehicle_count view는 바로 count 결과를 반환하므로 추가 집계 없이 바로 조회할 수 있다.
- *_units / *_vehicles view는 상세 목록용 view다.

## v_current_friendly_units
- Purpose: 현재 시점 아군 유닛 상세 목록
- Key columns: ref_datetime, unitname, groupname, unittype, posx, posy, posz, damage, objectparent
- Use when: 현재 아군 유닛 목록, 현재 아군 위치, 현재 아군 상태

## v_initial_friendly_units
- Purpose: 최초 시점 아군 유닛 상세 목록
- Key columns: ref_datetime, unitname, groupname, unittype, posx, posy, posz, damage, objectparent
- Use when: 원래 아군 유닛 목록, 최초 아군 배치

## v_current_enemy_units
- Purpose: 현재 시점 적군 유닛 상세 목록
- Key columns: ref_datetime, unitname, groupname, unittype, posx, posy, posz, damage, objectparent
- Use when: 현재 적군 유닛 목록, 현재 적군 위치, 현재 적군 상태

## v_initial_enemy_units
- Purpose: 최초 시점 적군 유닛 상세 목록
- Key columns: ref_datetime, unitname, groupname, unittype, posx, posy, posz, damage, objectparent
- Use when: 원래 적군 유닛 목록, 최초 적군 배치

## v_current_friendly_unit_count
- Purpose: 현재 아군 유닛 수
- Key columns: ref_datetime, unit_count
- Use when: 현재 아군 유닛 개수, 현재 남은 아군 병력 수

## v_initial_friendly_unit_count
- Purpose: 최초 아군 유닛 수
- Key columns: ref_datetime, unit_count
- Use when: 원래 아군 유닛 개수, 시작 시점 아군 병력 수

## v_current_enemy_unit_count
- Purpose: 현재 적군 유닛 수
- Key columns: ref_datetime, unit_count
- Use when: 현재 적군 유닛 개수, 현재 남은 적군 병력 수

## v_initial_enemy_unit_count
- Purpose: 최초 적군 유닛 수
- Key columns: ref_datetime, unit_count
- Use when: 원래 적군 유닛 개수, 시작 시점 적군 병력 수

## v_current_friendly_vehicles
- Purpose: 현재 시점 아군 장비 상세 목록
- Key columns: ref_datetime, vehiclename, groupname, vehicletype, posx, posy, posz, damage
- Use when: 현재 아군 장비 목록, 현재 아군 차량 상태, 현재 아군 장비 위치

## v_initial_friendly_vehicles
- Purpose: 최초 시점 아군 장비 상세 목록
- Key columns: ref_datetime, vehiclename, groupname, vehicletype, posx, posy, posz, damage
- Use when: 원래 아군 장비 목록, 시작 시점 아군 차량 배치

## v_current_enemy_vehicles
- Purpose: 현재 시점 적군 장비 상세 목록
- Key columns: ref_datetime, vehiclename, groupname, vehicletype, posx, posy, posz, damage
- Use when: 현재 적군 장비 목록, 현재 적군 차량 상태, 현재 적군 장비 위치

## v_initial_enemy_vehicles
- Purpose: 최초 시점 적군 장비 상세 목록
- Key columns: ref_datetime, vehiclename, groupname, vehicletype, posx, posy, posz, damage
- Use when: 원래 적군 장비 목록, 시작 시점 적군 차량 배치

## v_current_friendly_vehicle_count
- Purpose: 현재 아군 장비 수
- Key columns: ref_datetime, vehicle_count
- Use when: 현재 아군 장비 개수, 현재 아군 차량 수

## v_initial_friendly_vehicle_count
- Purpose: 최초 아군 장비 수
- Key columns: ref_datetime, vehicle_count
- Use when: 원래 아군 장비 개수, 시작 시점 아군 차량 수

## v_current_enemy_vehicle_count
- Purpose: 현재 적군 장비 수
- Key columns: ref_datetime, vehicle_count
- Use when: 현재 적군 장비 개수, 현재 적군 차량 수

## v_initial_enemy_vehicle_count
- Purpose: 최초 적군 장비 수
- Key columns: ref_datetime, vehicle_count
- Use when: 원래 적군 장비 개수, 시작 시점 적군 차량 수

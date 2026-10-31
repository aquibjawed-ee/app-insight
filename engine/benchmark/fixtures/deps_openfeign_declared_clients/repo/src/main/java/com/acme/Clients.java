package com.acme;

@FeignClient(name = "inventory", url = "${inventory.url}")
interface Inventory {}
@FeignClient("pricing")
interface Pricing {}
@FeignClient(name = "${other.name}")
interface Other {}

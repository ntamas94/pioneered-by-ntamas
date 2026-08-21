#include <linux/module.h>
#include <linux/export-internal.h>
#include <linux/compiler.h>

MODULE_INFO(name, KBUILD_MODNAME);

__visible struct module __this_module
__section(".gnu.linkonce.this_module") = {
	.name = KBUILD_MODNAME,
	.init = init_module,
#ifdef CONFIG_MODULE_UNLOAD
	.exit = cleanup_module,
#endif
	.arch = MODULE_ARCH_INIT,
};

KSYMTAB_FUNC(snd_usb_register_platform_ops, "_gpl", "");
KSYMTAB_FUNC(snd_usb_unregister_platform_ops, "_gpl", "");
KSYMTAB_FUNC(snd_usb_rediscover_devices, "_gpl", "");
KSYMTAB_FUNC(snd_usb_find_suppported_substream, "_gpl", "");
KSYMTAB_FUNC(snd_usb_lock_shutdown, "_gpl", "");
KSYMTAB_FUNC(snd_usb_unlock_shutdown, "_gpl", "");
KSYMTAB_FUNC(snd_usb_autoresume, "_gpl", "");
KSYMTAB_FUNC(snd_usb_autosuspend, "_gpl", "");
KSYMTAB_FUNC(snd_usb_endpoint_prepare, "_gpl", "");
KSYMTAB_FUNC(snd_usb_find_csint_desc, "_gpl", "");
KSYMTAB_FUNC(snd_usb_find_format, "_gpl", "");
KSYMTAB_FUNC(snd_usb_find_substream_format, "_gpl", "");
KSYMTAB_FUNC(snd_usb_hw_params, "_gpl", "");
KSYMTAB_FUNC(snd_usb_hw_free, "_gpl", "");

SYMBOL_CRC(snd_usb_register_platform_ops, 0x4ff2de1f, "_gpl");
SYMBOL_CRC(snd_usb_unregister_platform_ops, 0xd64b1971, "_gpl");
SYMBOL_CRC(snd_usb_rediscover_devices, 0x48e0836a, "_gpl");
SYMBOL_CRC(snd_usb_find_suppported_substream, 0x8a8b6542, "_gpl");
SYMBOL_CRC(snd_usb_lock_shutdown, 0xbf240a83, "_gpl");
SYMBOL_CRC(snd_usb_unlock_shutdown, 0x63e24202, "_gpl");
SYMBOL_CRC(snd_usb_autoresume, 0xcb97874c, "_gpl");
SYMBOL_CRC(snd_usb_autosuspend, 0xf48051aa, "_gpl");
SYMBOL_CRC(snd_usb_endpoint_prepare, 0xc470a1dc, "_gpl");
SYMBOL_CRC(snd_usb_find_csint_desc, 0x0ff2c1e0, "_gpl");
SYMBOL_CRC(snd_usb_find_format, 0xb349e098, "_gpl");
SYMBOL_CRC(snd_usb_find_substream_format, 0xf23f833e, "_gpl");
SYMBOL_CRC(snd_usb_hw_params, 0x02a39eff, "_gpl");
SYMBOL_CRC(snd_usb_hw_free, 0xae393e6d, "_gpl");

static const struct modversion_info ____versions[]
__used __section("__versions") = {
	{ 0x9e1460e5, "media_devnode_remove" },
	{ 0x50d0889f, "usb_alloc_urb" },
	{ 0x6ff8aa27, "usb_autopm_put_interface" },
	{ 0x9e7d6bd0, "__udelay" },
	{ 0x01b11052, "usb_free_urb" },
	{ 0x4a3ad70e, "wait_for_completion_timeout" },
	{ 0x1ddb50a8, "kmemdup_array" },
	{ 0xb8342c83, "__kmalloc_noprof" },
	{ 0x5e515be6, "ktime_get_ts64" },
	{ 0x77bc13a0, "strim" },
	{ 0x725e7e62, "usb_get_current_frame_number" },
	{ 0xd582c533, "snd_ctl_add" },
	{ 0x85e7a0e1, "usb_alloc_coherent" },
	{ 0x3cbd5823, "snd_pcm_new" },
	{ 0x656e4a6e, "snprintf" },
	{ 0xa6257a2f, "complete" },
	{ 0x25153b79, "usb_ifnum_to_if" },
	{ 0x1c9e978f, "memdup_user" },
	{ 0x6f83a899, "snd_pcm_add_chmap_ctls" },
	{ 0x8810754a, "_find_first_bit" },
	{ 0x2f2321b2, "snd_card_register" },
	{ 0x38ecb24b, "snd_card_free" },
	{ 0x608741b5, "__init_swait_queue_head" },
	{ 0x347e8359, "snd_ump_block_new" },
	{ 0x92540fbf, "finish_wait" },
	{ 0x5d670410, "usb_register_driver" },
	{ 0x96848186, "scnprintf" },
	{ 0x99f25868, "snd_pcm_hw_constraint_minmax" },
	{ 0xb9da7f40, "param_array_ops" },
	{ 0x4829a47e, "memcpy" },
	{ 0x3b6c41ea, "kstrtouint" },
	{ 0x037a0cba, "kfree" },
	{ 0xa347e9e5, "__media_device_register" },
	{ 0x3b524741, "snd_card_rw_proc_new" },
	{ 0x68a24153, "snd_pcm_format_physical_width" },
	{ 0xc3055d20, "usleep_range_state" },
	{ 0x8c26d495, "prepare_to_wait_event" },
	{ 0xe2964344, "__wake_up" },
	{ 0xad36393d, "input_register_handle" },
	{ 0xb36dc1cd, "param_set_charp" },
	{ 0x34db050b, "_raw_spin_lock_irqsave" },
	{ 0xc5a6d97f, "snd_ctl_remove" },
	{ 0x44640255, "snd_ctl_free_one" },
	{ 0xba8fbd64, "_raw_spin_lock" },
	{ 0x6674bb2e, "snd_ctl_find_id" },
	{ 0x5a93d753, "media_create_intf_link" },
	{ 0xbfcb20f6, "media_create_pad_link" },
	{ 0x057d6f20, "usb_interrupt_msg" },
	{ 0x410597f0, "snd_ctl_new1" },
	{ 0x4af6ddf0, "kstrtou16" },
	{ 0x92997ed8, "_printk" },
	{ 0x8427cc7b, "_raw_spin_lock_irq" },
	{ 0xb29f6a64, "___ratelimit" },
	{ 0x8ddd8aad, "schedule_timeout" },
	{ 0x01000e51, "schedule" },
	{ 0x1b9ba5f0, "usb_reset_device" },
	{ 0xf0fdf6cb, "__stack_chk_fail" },
	{ 0xb2fcb56d, "queue_delayed_work_on" },
	{ 0x6cbbfc54, "__arch_copy_to_user" },
	{ 0xeecafa3b, "snd_ump_update_group_attrs" },
	{ 0x30395315, "snd_component_add" },
	{ 0xf5131535, "snd_pcm_hw_rule_add" },
	{ 0x4e280f98, "usb_submit_urb" },
	{ 0x09a5b50c, "_dev_info" },
	{ 0xbed43a41, "snd_usbmidi_suspend" },
	{ 0xc6cbbc89, "capable" },
	{ 0x167c5967, "print_hex_dump" },
	{ 0x476b165a, "sized_strscpy" },
	{ 0xa10079dd, "media_device_register_entity" },
	{ 0xcc6a729f, "snd_ctl_enum_info" },
	{ 0xe686e281, "snd_card_new" },
	{ 0xa6db1a41, "usb_urb_ep_type_check" },
	{ 0x4599c32f, "usb_pipe_type_check" },
	{ 0x435f4df2, "usb_match_id" },
	{ 0x1d685696, "__snd_usbmidi_create" },
	{ 0xfe487975, "init_wait_entry" },
	{ 0x8e857f46, "snd_ctl_boolean_mono_info" },
	{ 0xbb260be5, "_dev_err" },
	{ 0xaf8ccee1, "usb_free_coherent" },
	{ 0x2ceca092, "snd_ump_parse_endpoint" },
	{ 0x01c6491e, "snd_ump_transmit" },
	{ 0xb6c4379f, "system_percpu_wq" },
	{ 0x19909ca6, "snd_hwdep_new" },
	{ 0xc10dfa38, "input_open_device" },
	{ 0x1e6d26a8, "strstr" },
	{ 0xdd01ed55, "snd_ump_receive" },
	{ 0x4dfa8d4b, "mutex_lock" },
	{ 0xe72ccfaf, "snd_pcm_new_stream" },
	{ 0x90e6796e, "usb_driver_claim_interface" },
	{ 0x4b750f53, "_raw_spin_unlock_irq" },
	{ 0xf25c315b, "usb_control_msg" },
	{ 0xaafdc258, "strcasecmp" },
	{ 0x683ceb95, "snd_card_free_when_closed" },
	{ 0xe6e4c331, "snd_ctl_notify" },
	{ 0x5bd0433e, "usb_set_interface" },
	{ 0x1edb69d6, "ktime_get_raw_ts64" },
	{ 0x904a882b, "media_entity_pads_init" },
	{ 0x024dbdea, "snd_pcm_set_ops" },
	{ 0x9ec6ca96, "ktime_get_real_ts64" },
	{ 0xbcab6ee6, "sscanf" },
	{ 0xcefb0c9f, "__mutex_init" },
	{ 0x1a3b25be, "snd_pcm_set_managed_buffer" },
	{ 0x409e887c, "usb_deregister" },
	{ 0x4a4a5d40, "snd_ctl_rename" },
	{ 0x9787496b, "input_close_device" },
	{ 0xd35cce70, "_raw_spin_unlock_irqrestore" },
	{ 0x52f759a2, "media_remove_intf_link" },
	{ 0x3d72189b, "usb_string" },
	{ 0x726416b5, "snd_device_new" },
	{ 0x8d662c7e, "snd_pcm_period_elapsed_under_stream_lock" },
	{ 0x03e45bce, "input_unregister_handler" },
	{ 0xb9638db4, "snd_pcm_rate_to_rate_bit" },
	{ 0xdcb764ad, "memset" },
	{ 0x9d55c01b, "_dev_warn" },
	{ 0xf9c0b663, "strlcat" },
	{ 0xc4290c11, "param_ops_charp" },
	{ 0x9c68f08d, "param_get_charp" },
	{ 0x9d0129f8, "kmemdup_noprof" },
	{ 0xb8b7fc3a, "usb_get_descriptor" },
	{ 0xd9a5ea54, "__init_waitqueue_head" },
	{ 0xfb384d37, "kasprintf" },
	{ 0xa45c03d2, "snd_ump_attach_legacy_rawmidi" },
	{ 0xe2d5255a, "strcmp" },
	{ 0x15ba50a6, "jiffies" },
	{ 0x1ed88d6a, "kstrdup" },
	{ 0xe7b09250, "snd_card_disconnect" },
	{ 0x402a1534, "usb_unlink_urb" },
	{ 0xb2af19e1, "snd_usbmidi_resume" },
	{ 0xc12aac0b, "input_register_handler" },
	{ 0xd33ebf92, "usb_disable_autosuspend" },
	{ 0x14beb237, "usb_enable_autosuspend" },
	{ 0x85df9b6c, "strsep" },
	{ 0x3213f038, "mutex_unlock" },
	{ 0x87bf5473, "usb_autopm_get_interface" },
	{ 0x9fa7184a, "cancel_delayed_work_sync" },
	{ 0x522f8bd7, "param_ops_bool" },
	{ 0xaed62906, "media_device_delete" },
	{ 0x3147816e, "usb_reset_configuration" },
	{ 0x8320a874, "__kmalloc_cache_noprof" },
	{ 0x8b07079c, "usb_kill_urb" },
	{ 0xab1af175, "seq_printf" },
	{ 0x2ac8f4c6, "snd_pcm_stop_xrun" },
	{ 0xffeedf6a, "delayed_work_timer_fn" },
	{ 0xba0f1f31, "input_unregister_handle" },
	{ 0x12a4e128, "__arch_copy_from_user" },
	{ 0xaf23adcf, "usb_driver_set_configuration" },
	{ 0xdd9abee4, "snd_info_create_card_entry" },
	{ 0xe3f00cab, "snd_ump_endpoint_new" },
	{ 0xf9ddb5d9, "timer_init_key" },
	{ 0xa65c6def, "alt_cb_patch_nops" },
	{ 0x27479d14, "param_free_charp" },
	{ 0x7dc4e40d, "media_devnode_create" },
	{ 0x7a134cb5, "snd_pcm_period_elapsed" },
	{ 0x52e5ca0f, "media_device_unregister_entity" },
	{ 0x151f4898, "schedule_timeout_uninterruptible" },
	{ 0x98cf60b3, "strlen" },
	{ 0x489cbaa2, "param_ops_int" },
	{ 0xa286a234, "snd_pcm_format_name" },
	{ 0x5d04b58d, "usb_altnum_to_altsetting" },
	{ 0xb5b54b34, "_raw_spin_unlock" },
	{ 0xd9d2bb03, "snd_usbmidi_disconnect" },
	{ 0xf9a482f9, "msleep" },
	{ 0x18343d5a, "media_device_usb_allocate" },
	{ 0x5bd716e6, "kmalloc_caches" },
	{ 0x91d66ee9, "module_layout" },
};

MODULE_INFO(depends, "mc,snd,snd-pcm,snd-ump,snd-usbmidi-lib,snd-hwdep");

MODULE_ALIAS("usb:v0403pB8D8d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v041Ep0005d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v041Ep3F02d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v041Ep3F04d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v041Ep3F0Ad*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v041Ep3F19d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v31B2p0011d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v041Ep4095d*dc*dsc*dp*ic01isc01ip*in*");
MODULE_ALIAS("usb:v0424pB832d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v046Dp0850d*dc*dsc*dp*ic01isc01ip*in*");
MODULE_ALIAS("usb:v046Dp08AEd*dc*dsc*dp*ic01isc01ip*in*");
MODULE_ALIAS("usb:v046Dp08C6d*dc*dsc*dp*ic01isc01ip*in*");
MODULE_ALIAS("usb:v046Dp08F0d*dc*dsc*dp*ic01isc01ip*in*");
MODULE_ALIAS("usb:v046Dp08F5d*dc*dsc*dp*ic01isc01ip*in*");
MODULE_ALIAS("usb:v046Dp08F6d*dc*dsc*dp*ic01isc01ip*in*");
MODULE_ALIAS("usb:v046Dp0990d*dc*dsc*dp*ic01isc01ip*in*");
MODULE_ALIAS("usb:v0499p1000d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1001d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1002d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1003d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1004d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0499p1005d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1006d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1007d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1008d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1009d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p100Ad*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0499p100Cd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p100Dd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p100Ed*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p100Fd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1010d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1011d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1012d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1013d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1014d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1015d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1016d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1017d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1018d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1019d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p101Ad*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p101Bd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p101Cd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p101Dd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p101Ed*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p101Fd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1020d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1021d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1022d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1023d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1024d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1025d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1026d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1027d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1028d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1029d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p102Ad*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p102Bd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p102Ed*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1030d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1031d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1032d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1033d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1034d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1035d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1036d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1037d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1038d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1039d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p103Ad*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p103Bd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p103Cd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p103Dd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p103Ed*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p103Fd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1040d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1041d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1042d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1043d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1044d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1045d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p104Ed*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0499p104Fd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1050d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1051d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1052d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1053d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0499p1054d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0499p1055d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1056d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1057d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1058d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1059d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p105Ad*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p105Bd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p105Cd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p105Dd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1503d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1507d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1509d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p150Ad*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p150Cd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p1718d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p2000d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p2001d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p2002d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p2003d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p5000d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p5001d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p5002d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p5003d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p5004d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p5005d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p5006d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p5007d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p5008d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p5009d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p500Ad*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p500Bd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p500Cd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p500Dd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p500Ed*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p500Fd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p7000d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p7010d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0499p*d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0582p0000d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0002d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0003d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0004d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0005d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0007d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0008d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0009d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p000Bd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p000Cd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0010d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0012d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0014d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0016d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p001Bd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p001Dd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0023d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0025d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0027d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0029d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p002Bd*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0582p002Dd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p002Fd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0033d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0037d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p003Bd*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0582p0040d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0042d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0047d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0048d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p004Cd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p004Dd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0050d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0052d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0060d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0064d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0065d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p006Dd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0074d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0582p0075d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p007Ad*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0582p0080d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p008Bd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p00A3d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p00C4d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p00E6d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0582p0108d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0582p0113d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0120d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p012Fd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0159d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p0044d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p007Dd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p008Dd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0582p*d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v06F8pB000d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p1002d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p1011d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p1015d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p1021d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p1031d010dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0763p1033d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p1041d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p2001d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p2003d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p2008d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p200Dd*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p2019d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0763p201Ad*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p2030d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p2031d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p2080d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0763p2081d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v07CFp6801d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v07CFp6802d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v07FDp0001d*dc*dsc02dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v086Ap0001d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v086Ap0002d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v086Ap0003d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0944p0200d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0944p0201d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0944p0204d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v09E8p0062d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v09E8p0021d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0A4Ep2040d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0A4Ep4040d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0CCDp0012d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0CCDp0013d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0CCDp0014d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v0CCDp0035d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v103Dp0100d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v103Dp0101d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1235p0001d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v1235p0002d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v1235p000Ad*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1235p000Ed*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1235p0010d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1235p0018d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1235p4661d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v133Ep0815d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v17CCp1000d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v17CCp1010d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v17CCp1020d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p752Dd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1F38p0001d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v4752p0011d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v7104p2202d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0DBAp1000d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0DBAp3000d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0DBAp5000d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v0644p8021d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v154Ep500Ed*dc*dsc*dp*ic01isc01ip*in*");
MODULE_ALIAS("usb:v045Ep0283d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v200Cp100Bd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1686p00DDd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v*p*d*dc*dsc*dp*ic01isc03ip*in*");
MODULE_ALIAS("usb:v13E5p0001d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v19B5p0021d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v07FDp0004d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v2B73p0023d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v2B73p0017d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v2B73p000Ed*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v2B73p000Dd*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v2B73p001Ed*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v2B73p000Ad*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v2B73p0020d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v2B73p0029d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v2B73p003Cd*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v2B73p0034d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v534Dp0021d*dc*dsc*dp*ic01isc01ip*in*");
MODULE_ALIAS("usb:v534Dp2109d*dc*dsc*dp*ic01isc01ip*in*");
MODULE_ALIAS("usb:v08E4p017Fd*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v2B73p001Bd*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v08E4p0163d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v2B73p0013d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v1395p0300d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v2B53p0023d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v2B53p0024d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v2B53p0031d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:vFFADpA001d*dc*dsc*dp*icFFisc*ip*in*");
MODULE_ALIAS("usb:v2A39p3F8Cd*dc*dsc*dp*icFFisc*ip*in00*");
MODULE_ALIAS("usb:v2A39p3FA0d*dc*dsc*dp*icFFisc*ip*in00*");
MODULE_ALIAS("usb:v*p*d*dc*dsc*dp*ic01isc01ip*in*");

MODULE_INFO(srcversion, "5BC405B3D1B65788E0B29CF");
